# Service Layout — Claim Runner Pod

The pod repository contains four independently runnable services and a shared data layer, plus central startup tooling at the repository root.

## Directory Structure

```
claim-runner/
├── data-service/            # Data Service API — port 8083
├── claims-manager/          # Claims Manager API — port 8080
├── benefits-determiner/     # Benefits Determiner API — port 8081
├── pricer/                  # Pricer API — port 8082
├── data/                    # Shared JSON data files (read by Data Service only)
│   ├── members.json         # Read-only at runtime
│   ├── plans.json           # Read-only at runtime
│   ├── fee_schedules.json   # Read-only at runtime
│   └── claims.json          # Written by Data Service after each POST /claims
└── start.sh                 # Central startup script
```

Each service directory is self-contained: it holds its own source, its own dependency manifest, and its own per-service startup command. A service can be started in isolation for development or testing without requiring the others to be running.

## Central Startup

`start.sh` at the repository root starts all four services in dependency order:

1. Data Service (port 8083) — reads from disk; no upstream HTTP dependencies
2. Benefits Determiner (port 8081) — waits on Data Service `/health`
3. Pricer (port 8082) — waits on Data Service `/health` (starts concurrently with Benefits Determiner)
4. Claims Manager (port 8080) — waits on Benefits Determiner, Pricer, and Data Service `/health`

The script waits for each service's `/health` endpoint to return 200 before starting dependents. Benefits Determiner and Pricer can start concurrently once the Data Service is healthy. Startup is complete when all four `/health` checks pass.

Service URLs are passed via environment variables, so the central script can override them for non-default configurations without editing service source.

## Service Separation Principle

Each service is independently startable, independently testable, and independently deployable. No service imports code from another service directory. The only coupling between services at runtime is the HTTP contracts defined in `architecture/inter-service-contracts.md`.

This separation is the primary architectural constraint for the practicum: it allows learners to work on one service in isolation, verify it against its contract, and integrate it with the others only through the defined HTTP interface.

## Implementation Wave Order

Spec numbers in this pod reflect intake capture order, not build priority. The implementation dependency graph requires a specific wave sequence that differs from the numeric order of the specs.

```
Wave 1 — Data foundation (no upstream HTTP dependencies)
  claim-runner/0004  Seed Data Generation
    Produces data/plans.json, data/fee_schedules.json, and data/members.json.
    data/claims.json is auto-created by the Data Service on first startup.
    Nothing can be end-to-end tested until these files exist.

Wave 2 — Data layer (requires Wave 1 output files on disk)
  claim-runner/0005  Data Service API  (port 8083)
    Loads the Wave 1 files at startup.
    All three adjudication services call this service for every data access.
    No adjudication service can be end-to-end tested until this is healthy.

Wave 3 — Adjudication services (requires Wave 2 healthy; 0002 and 0003 may proceed in parallel)
  claim-runner/0002  Benefits Determiner  (port 8081)
  claim-runner/0003  Pricer               (port 8082)
  claim-runner/0001  Claims Manager       (port 8080)  ← last; orchestrates 0002 and 0003
```

Each Wave 3 service can be implemented and unit-tested against a stub Data Service before Wave 2 is complete. Full integration testing of any adjudication path requires all three waves to be complete and all four `/health` endpoints to be passing.

The runtime startup order in the **Central Startup** section above reflects this same dependency structure.

## Data File Access

The Data Service is the only service that reads from or writes to `data/`. It loads all four files into memory at startup and exposes them via HTTP. The three adjudication services call the Data Service for all data access; they have no direct dependency on the `data/` directory.

| Variable | Used by | Default |
|---|---|---|
| `DATA_DIR` | Data Service only | `./data` |
| `DATA_SERVICE_URL` | Claims Manager, Benefits Determiner, Pricer | `http://localhost:8083` |

Claims Manager writes new claim records through `POST /claims` on the Data Service. The Data Service persists the updated record to `claims.json` synchronously. Accumulator balances are seeded in `members.json` and not updated — see `architecture/data-model.md` for the known limitations.
