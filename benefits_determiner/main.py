import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .models import DataServiceError, DetermineRequest, DetermineResponse, LineDetermination
from . import data_client, determination

DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://localhost:8083")
PORT = int(os.environ.get("PORT", "8081"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Benefits Determiner listening on port {PORT}, DATA_SERVICE_URL={DATA_SERVICE_URL}", flush=True)
    app.state.http_client = httpx.Client(timeout=10.0)
    yield
    app.state.http_client.close()


app = FastAPI(title="Benefits Determiner", lifespan=lifespan)


@app.exception_handler(DataServiceError)
async def data_service_error_handler(request: Request, exc: DataServiceError):
    return JSONResponse(status_code=503, content={"detail": "Data Service unavailable"})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/benefits/determine", response_model=DetermineResponse)
def determine_benefits(request: DetermineRequest, http_request: Request):
    client: httpx.Client = http_request.app.state.http_client

    member = data_client.get_member(client, DATA_SERVICE_URL, request.member_id)
    if member is None:
        return DetermineResponse(
            member_id=request.member_id,
            plan_id=None,
            eligible=False,
            network_status=None,
            overall_covered=False,
            line_determinations=[],
            denial_reason="NOT_ELIGIBLE",
        )

    eligible, denial_reason = determination.check_eligibility(
        member["enrollment"], request.date_of_service
    )
    if not eligible:
        return DetermineResponse(
            member_id=request.member_id,
            plan_id=None,
            eligible=False,
            network_status=None,
            overall_covered=False,
            line_determinations=[],
            denial_reason=denial_reason,
        )

    plan_id = member["enrollment"]["plan_id"]
    plan = data_client.get_plan(client, DATA_SERVICE_URL, plan_id)
    if plan is None:
        raise DataServiceError(f"Plan {plan_id} not found in Data Service")

    network_status = determination.check_network(plan, request.provider_id)

    line_determinations = [
        determination.evaluate_line(code, plan, member.get("authorizations", []), request.date_of_service)
        for code in request.procedure_codes
    ]

    overall_covered = determination.compute_overall_covered(line_determinations)

    return DetermineResponse(
        member_id=request.member_id,
        plan_id=plan_id,
        eligible=True,
        network_status=network_status,
        overall_covered=overall_covered,
        line_determinations=line_determinations,
        denial_reason=None,
    )
