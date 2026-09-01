# Claim Runner Pod — Constitution

This file has two blocks. The first block (Core Principles) is the canonical governed block distributed by the control pod and protected by CODEOWNERS. The second block (Pod-Local Principles) is authored by the control pod for this pod specifically. Both blocks must be respected by every spec, plan, and implementation in this repository.

Amendments to the Core Principles block require a control pod decision on record. Amendments to the Pod-Local Principles block require a pull request reviewed by the control pod.

---

## Core Principles

These principles form the governed block of every engineering pod's constitution. They are distributed from `canonical/constitution/core-principles.md` in the control pod repository.

Principles marked **non-negotiable** are enforced mechanically at plan time and may not be waived by a pod without a control pod decision on record. All other principles are strong defaults; a pod that departs from one must record its reasoning in its own `decisions/`.

### API Contracts

**Every service exposes a `/health` endpoint.** `GET /health` must return HTTP 200 when the service is running and able to accept requests. No other behavior is specified; a minimal response body is acceptable. *Non-negotiable.*

**API contracts are specified before implementation begins.** The interface a service exposes — paths, request shapes, response shapes, error codes — must be documented in the pod's `architecture/` before a spec enters the plan phase. Implementation that deviates from the documented contract requires the architecture document to be updated first, not after.

**Breaking changes to inter-service contracts require coordinated updates.** A change that alters an existing request or response field, removes a field, or changes a status code is a breaking change. The implementing service and all callers must be updated in the same spec. Additive changes (new optional fields) are non-breaking and do not require coordination.

### Testing

**The primary success path must have an integration test before a spec is marked complete.** An integration test exercises the full call chain from the external entry point through all downstream services against real (or realistic mock) data. Unit tests alone do not satisfy this requirement. *Non-negotiable.*

**Tests must not hardcode port numbers or file paths.** Both are configurable via environment variables. A test suite that breaks when a port or data directory changes is not portable and will fail in practicum environments that differ from the author's machine.

### Data and State

**Services read configuration from environment variables, not from hardcoded values.** Service URLs, data file paths, and port numbers must be settable without editing source code. Each must have a documented default that works when the repository is cloned and started with no environment configuration.

**No service may introduce an external runtime dependency not present in the repository.** An external runtime dependency is anything that requires a separate installation step beyond what the service's own startup instructions describe — a running database, a message broker, a remote API. The practicum runs on a single machine with no external services.

### Observability

**Startup and shutdown must be logged to stdout.** A service starting up must emit at minimum: the port it is listening on and the data files it has loaded. A service shutting down must emit a shutdown message. This is the minimum needed for a learner to verify that central startup completed correctly.

---

## Pod-Local Principles

These principles are authored by the control pod for the claim-runner pod specifically.

### Claim Type

**This system processes professional claims only (CMS-1500 / 837P).** No spec may extend the system to accept institutional claims (CMS-1450 / UB-04 / 837I). A spec proposing institutional claim support is out of scope for this pod and must be declined at allocation review. This is a permanent constraint for the practicum, not a deferral.

### Technology Stack

**All three services are implemented in Python using FastAPI.** No spec may introduce a different language or web framework for any service in this pod. A spec that proposes migrating a service to another stack is out of scope for the practicum.

**Each service declares its dependencies in its own `requirements.txt`.** There is no shared package manifest at the repository root. A dependency needed by more than one service is listed independently in each service's `requirements.txt` — it is not duplicated, and it is not placed inside any single service directory.

**The Python version is fixed at 3.11 or later.** Features below 3.11 (e.g., `match` statements, `tomllib`) may be used freely.

### Service Independence

**Each service must be independently startable.** Starting Benefits Determiner or Pricer must not require Claims Manager to be running, and vice versa. A developer working on one service must be able to run it in isolation against the shared data files without bringing up the full system.

**Services may not import code from each other's directories.** The only permitted coupling between services is the HTTP contracts documented in `architecture/inter-service-contracts.md`. A shared utility needed by more than one service is extracted to a `shared/` directory at the repository root and imported by both — it is not duplicated, and it is not placed inside any single service directory.

### Data Layer

**JSON files in `data/` are the intended and permanent data layer.** No spec may introduce a dependency on an external database, cache, or message broker. The practicum runs on a single machine with no external services, and that constraint holds for the lifetime of this system.

**`members.json`, `plans.json`, and `fee_schedules.json` are read-only at runtime.** No service may write to these files during normal operation. Accumulator balances are seeded manually and are not updated after adjudication — this is an acknowledged practicum limitation.

**Claims Manager writes to `claims.json` after each adjudication.** This is the only file any service may write to. `claims.json` is the durable claim ledger and the backing store for `GET /claims/{claim_id}`.

**Each service resolves the data directory path from the `DATA_DIR` environment variable.** The default is `./data` relative to the repository root. Hardcoded paths to data files are not permitted.

### Spec Scope

**Each specification may touch exactly one API service.** A spec for the Pricer may not also modify the Benefits Determiner or Claims Manager contracts, data models, or behavior. A spec for Claims Manager may not also change Pricer or Benefits Determiner internals.

This applies to every artifact in the spec: request/response shapes, data file changes, error codes, business logic, and test cases. If a change genuinely requires coordinated updates across two services, it must be decomposed into two separate specs — one per service — and allocated in sequence, with the consumer spec blocked on the provider spec landing first.

### Adjudication Flow

**Claims Manager is the sole orchestrator.** Benefits Determiner and Pricer do not call each other and do not call Claims Manager. Any new service added to the pod must fit this pattern: either it is called by Claims Manager, or it is a standalone utility. Peer-to-peer calls between non-orchestrator services are not permitted without a decision on record.

**`plan_id` and `network_status` flow from Benefits Determiner to Pricer through Claims Manager.** Claims Manager must not re-derive these values from its own data. It passes them forward from the Benefits Determiner response.

### Central Startup

**`start.sh` is the single authoritative way to start the full system.** It starts services in dependency order (Benefits Determiner and Pricer before Claims Manager) and gates each step on the upstream service's `/health` endpoint returning 200.

**`start.sh` is POSIX shell with no external dependencies beyond what the services themselves require.** It must work on any machine where the three services can be started individually.

---

**Version**: 1.0 | **Issued**: 2026-08-30 | **Issuing pod**: control
