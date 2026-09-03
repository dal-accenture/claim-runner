import os
from contextlib import asynccontextmanager
from decimal import Decimal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from .models import (
    AccumulatorSnapshot, ClaimTotals, DataServiceError,
    LineDetail, MemberNotFoundError, PlanNotFoundError,
    PriceRequest, PriceResponse,
)
from . import data_client, pricing

DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://localhost:8083")
PORT = int(os.environ.get("PORT", "8082"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Pricer listening on port {PORT}, DATA_SERVICE_URL={DATA_SERVICE_URL}", flush=True)
    app.state.http_client = httpx.Client(timeout=10.0)
    yield
    app.state.http_client.close()


app = FastAPI(title="Pricer", lifespan=lifespan)


@app.exception_handler(DataServiceError)
async def data_service_error_handler(request: Request, exc: DataServiceError):
    return JSONResponse(status_code=503, content={"detail": "Data Service unavailable"})


@app.exception_handler(MemberNotFoundError)
async def member_not_found_handler(request: Request, exc: MemberNotFoundError):
    return JSONResponse(status_code=404, content={"detail": f"Member {exc.member_id} not found"})


@app.exception_handler(PlanNotFoundError)
async def plan_not_found_handler(request: Request, exc: PlanNotFoundError):
    return JSONResponse(status_code=404, content={"detail": f"Plan {exc.plan_id} not found"})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/price", response_model=PriceResponse)
def price_claim(request: PriceRequest, http_request: Request):
    client = http_request.app.state.http_client

    member = data_client.get_member(client, DATA_SERVICE_URL, request.member_id)
    data_client.get_plan(client, DATA_SERVICE_URL, request.plan_id)

    fee_schedule_cache: dict[str, dict] = {}
    unique_codes = {line.procedure_code for line in request.claim_lines}
    for code in unique_codes:
        fs = data_client.get_fee_schedule(client, DATA_SERVICE_URL, code)
        if fs is None:
            raise HTTPException(
                status_code=422,
                detail=f"Procedure code {code} not found in fee schedules",
            )
        fee_schedule_cache[code] = fs

    accumulators = member.get("accumulators", {})
    deductible_used = Decimal("0")
    oop_used = Decimal("0")
    line_details = []

    for line in request.claim_lines:
        fs = fee_schedule_cache[line.procedure_code]
        fs_block = fs["in_network"] if request.network_status == "IN_NETWORK" else fs["out_of_network"]

        allowed_amount, contractual_adjustment = pricing.compute_allowed(line, fs_block)

        (
            deductible_applied,
            copay_applied,
            coinsurance_applied,
            member_liability,
            payer_liability,
            deductible_used,
            oop_used,
        ) = pricing.apply_cost_sharing(
            allowed_amount, fs_block, accumulators, deductible_used, oop_used
        )

        arc = "CO-45" if contractual_adjustment > Decimal("0") else None
        line_details.append(
            {
                "line_number": line.line_number,
                "procedure_code": line.procedure_code,
                "billed_amount": line.billed_amount * line.units,
                "allowed_amount": allowed_amount,
                "contractual_adjustment": contractual_adjustment,
                "deductible_applied": deductible_applied,
                "copay_applied": copay_applied,
                "coinsurance_applied": coinsurance_applied,
                "member_liability": member_liability,
                "payer_liability": payer_liability,
                "adjustment_reason_code": arc,
                "line_status": "PAID",
            }
        )

    totals = pricing.compute_totals(line_details)
    snapshot = pricing.compute_snapshot(accumulators, deductible_used, oop_used)

    return PriceResponse(
        claim_id=request.claim_id,
        totals=ClaimTotals(**totals),
        accumulator_snapshot=AccumulatorSnapshot(**snapshot),
        line_detail=[LineDetail(**ld) for ld in line_details],
    )
