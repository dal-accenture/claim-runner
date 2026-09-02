import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("data_service")

_members: dict = {}
_plans: dict = {}
_fee_schedules: dict = {}
_claims: dict = {}
_lock = asyncio.Lock()


def _load_all_data() -> None:
    global _members, _plans, _fee_schedules, _claims
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    port = os.getenv("PORT", "8083")

    for fname in ("members.json", "plans.json", "fee_schedules.json"):
        if not (data_dir / fname).exists():
            logger.critical(f"Required data file missing: {data_dir / fname}")
            sys.exit(1)

    with open(data_dir / "members.json") as f:
        _members = {r["member_id"]: r for r in json.load(f)}

    with open(data_dir / "plans.json") as f:
        _plans = {r["plan_id"]: r for r in json.load(f)}

    with open(data_dir / "fee_schedules.json") as f:
        _fee_schedules = {r["procedure_code"]: r for r in json.load(f)}

    claims_path = data_dir / "claims.json"
    if not claims_path.exists():
        logger.info(f"claims.json not found at {claims_path}; initializing empty claims store")
        _claims = {}
    else:
        with open(claims_path) as f:
            _claims = {r["claim_id"]: r for r in json.load(f)}

    logger.info(
        f"Data Service starting on port {port} — "
        f"members={len(_members)}, plans={len(_plans)}, "
        f"fee_schedules={len(_fee_schedules)}, claims={len(_claims)}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_all_data()
    yield
    logger.info("Data Service shutting down")


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "UP",
        "members": len(_members),
        "plans": len(_plans),
        "fee_schedules": len(_fee_schedules),
        "claims": len(_claims),
    }


@app.get("/members/{member_id}")
async def get_member(member_id: str):
    if member_id not in _members:
        logger.info(f"404 member not found: {member_id}")
        raise HTTPException(status_code=404, detail="member not found")
    return _members[member_id]


@app.get("/plans/{plan_id}")
async def get_plan(plan_id: str):
    if plan_id not in _plans:
        logger.info(f"404 plan not found: {plan_id}")
        raise HTTPException(status_code=404, detail="plan not found")
    return _plans[plan_id]


@app.get("/fee-schedules/{procedure_code}")
async def get_fee_schedule(procedure_code: str):
    if procedure_code not in _fee_schedules:
        logger.info(f"404 procedure code not found: {procedure_code}")
        raise HTTPException(status_code=404, detail="procedure code not found")
    return _fee_schedules[procedure_code]


@app.get("/claims/{claim_id}")
async def get_claim(claim_id: str):
    if claim_id not in _claims:
        logger.info(f"404 claim not found: {claim_id}")
        raise HTTPException(status_code=404, detail="claim not found")
    return _claims[claim_id]


class ClaimBody(BaseModel):
    claim_id: str
    model_config = {"extra": "allow"}


@app.post("/claims", status_code=201)
async def post_claim(body: ClaimBody):
    claim_id = body.claim_id
    if claim_id in _claims:
        logger.info(f"POST /claims 409 duplicate claim_id: {claim_id}")
        raise HTTPException(status_code=409, detail="claim already exists")
    record = body.model_dump()
    async with _lock:
        _claims[claim_id] = record
    logger.info(f"POST /claims 201 stored: {claim_id}")
    return JSONResponse(content=record, status_code=201)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8083")))
