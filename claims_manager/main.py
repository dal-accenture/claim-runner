from __future__ import annotations
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx

from .models import (
    AdjudicationResult, BatchRequest, BatchResponse, ClaimTotals,
    DataServiceError, BenefitsDeterminerError, PricerError,
    LineDetailEntry,
)
from . import data_client, adjudication

DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://localhost:8083")
BENEFITS_DETERMINER_URL = os.environ.get("BENEFITS_DETERMINER_URL", "http://localhost:8081")
PRICER_URL = os.environ.get("PRICER_URL", "http://localhost:8082")
PORT = int(os.environ.get("PORT", "8080"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(
        f"Claims Manager listening on port {PORT}, "
        f"DATA_SERVICE_URL={DATA_SERVICE_URL}, "
        f"BENEFITS_DETERMINER_URL={BENEFITS_DETERMINER_URL}, "
        f"PRICER_URL={PRICER_URL}",
        flush=True,
    )
    app.state.http_client = httpx.Client(timeout=10.0)
    yield
    app.state.http_client.close()
    print("Claims Manager shutting down.", flush=True)


app = FastAPI(title="Claims Manager", lifespan=lifespan)


@app.exception_handler(DataServiceError)
async def data_service_error_handler(request: Request, exc: DataServiceError):
    return JSONResponse(status_code=503, content={"detail": "Service unavailable"})


@app.exception_handler(BenefitsDeterminerError)
async def bd_error_handler(request: Request, exc: BenefitsDeterminerError):
    return JSONResponse(status_code=503, content={"detail": "Service unavailable"})


@app.exception_handler(PricerError)
async def pricer_error_handler(request: Request, exc: PricerError):
    return JSONResponse(status_code=503, content={"detail": "Service unavailable"})


@app.get("/health")
def health():
    return {"status": "UP"}


@app.post("/claims/batch", response_model=BatchResponse)
def submit_batch(request: BatchRequest, http_request: Request):
    client = http_request.app.state.http_client
    seen_ids: set[str] = set()
    results: list[AdjudicationResult] = []

    for claim in request.claims:
        # --- FR-2: Field validation ---
        errors = adjudication.validate_claim(claim, seen_ids)
        if errors:
            results.append(AdjudicationResult(
                claim_id=claim.claim_id or "",
                status="VALIDATION_ERROR",
                adjudicated_at=None,
                totals=None,
                denial_reasons=[],
                errors=errors,
                line_detail=[],
            ))
            if claim.claim_id:
                seen_ids.add(claim.claim_id)
            continue

        seen_ids.add(claim.claim_id)

        # --- Dedup check: claim_id already in Data Service ---
        existing = data_client.get_claim(client, DATA_SERVICE_URL, claim.claim_id)
        if existing is not None:
            results.append(AdjudicationResult(
                claim_id=claim.claim_id,
                status="CONFLICT",
                adjudicated_at=None,
                totals=None,
                denial_reasons=[],
                errors=["claim_id already exists"],
                line_detail=[],
            ))
            continue

        # --- FR-3: Member existence check ---
        member = data_client.get_member(client, DATA_SERVICE_URL, claim.member_id)
        if member is None:
            results.append(AdjudicationResult(
                claim_id=claim.claim_id,
                status="DENIED",
                adjudicated_at=_now_utc(),
                totals=ClaimTotals(
                    billed_amount=sum(l.billed_amount * l.units for l in claim.claim_lines),
                    allowed_amount=0,
                    member_liability=0,
                    payer_liability=0,
                ),
                denial_reasons=["NOT_ELIGIBLE"],
                errors=[],
                line_detail=[],
            ))
            continue

        # --- FR-4: Orchestration ---
        bd_resp = data_client.determine_benefits(client, BENEFITS_DETERMINER_URL, {
            "member_id": claim.member_id,
            "provider_id": claim.provider_id,
            "procedure_codes": [l.procedure_code for l in claim.claim_lines],
            "date_of_service": claim.date_of_service,
        })

        # Build lookup: procedure_code → line_determination
        ld_by_code: dict[str, dict] = {
            ld["procedure_code"]: ld for ld in bd_resp.get("line_determinations", [])
        }

        covered_lines = [l for l in claim.claim_lines if ld_by_code.get(l.procedure_code, {}).get("covered", False)]
        denied_lines = [l for l in claim.claim_lines if not ld_by_code.get(l.procedure_code, {}).get("covered", False)]

        line_details: list[dict] = []

        if covered_lines:
            price_resp = data_client.price_claim(client, PRICER_URL, {
                "claim_id": claim.claim_id,
                "member_id": claim.member_id,
                "plan_id": bd_resp["plan_id"],
                "network_status": bd_resp["network_status"],
                "claim_lines": [
                    {
                        "line_number": l.line_number,
                        "procedure_code": l.procedure_code,
                        "units": l.units,
                        "billed_amount": float(l.billed_amount),
                    }
                    for l in covered_lines
                ],
            })
            pricer_lines_by_num = {ld["line_number"]: ld for ld in price_resp["line_detail"]}
        else:
            pricer_lines_by_num = {}

        # Merge in original claim line order
        for line in claim.claim_lines:
            det = ld_by_code.get(line.procedure_code, {})
            if det.get("covered", False):
                pl = pricer_lines_by_num[line.line_number]
                line_details.append({
                    "line_number": pl["line_number"],
                    "procedure_code": pl["procedure_code"],
                    "billed_amount": pl["billed_amount"],
                    "allowed_amount": pl["allowed_amount"],
                    "contractual_adjustment": pl.get("contractual_adjustment", 0.0),
                    "deductible_applied": pl["deductible_applied"],
                    "copay_applied": pl["copay_applied"],
                    "coinsurance_applied": pl["coinsurance_applied"],
                    "member_liability": pl["member_liability"],
                    "payer_liability": pl["payer_liability"],
                    "adjustment_reason_code": pl.get("adjustment_reason_code"),
                    "denial_reason": None,
                    "line_status": "PAID",
                })
            else:
                line_details.append(
                    adjudication.build_denied_line(line, det.get("denial_reason") or "NOT_COVERED")
                )

        totals_dict = adjudication.compute_claim_totals(line_details)
        status = adjudication.determine_claim_status(line_details)

        results.append(AdjudicationResult(
            claim_id=claim.claim_id,
            status=status,
            adjudicated_at=_now_utc(),
            totals=ClaimTotals(**totals_dict),
            denial_reasons=[],
            errors=[],
            line_detail=[LineDetailEntry(**ld) for ld in line_details],
        ))

    # Write adjudicated results to Data Service
    for result in results:
        if result.status in ("PAID", "DENIED", "PARTIALLY_PAID"):
            data_client.post_claim(client, DATA_SERVICE_URL, result.model_dump(mode="json"))

    return BatchResponse(results=results)


@app.get("/claims/{claim_id}")
def get_claim(claim_id: str, http_request: Request):
    client = http_request.app.state.http_client
    result = data_client.get_claim(client, DATA_SERVICE_URL, claim_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    return result


def _now_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
