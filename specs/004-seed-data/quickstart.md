# Quickstart Validation Guide: Seed Data Generation

**Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

---

## Prerequisites

- Python 3.11+ installed
- Working directory: repository root

---

## Generate the seed data

```bash
python scripts/generate_seed_data.py
```

Expected output (stdout):

```
Seed data generation complete.
  plans.json:         5 records
  fee_schedules.json: 25 records
  members.json:       200 records
  claims.json:        153 records   # exact count varies by scenario build
Written to: data/
```

Re-running is safe — the script overwrites existing files and produces identical output every time (fixed seed).

---

## Validate output manually

### 1. Record counts

```bash
python -c "
import json, pathlib
d = pathlib.Path('data')
for f in ['plans.json','fee_schedules.json','members.json','claims.json']:
    data = json.loads((d/f).read_text())
    print(f'{f}: {len(data)} records')
"
```

Expected:
```
plans.json: 5 records
fee_schedules.json: 25 records
members.json: 200 records
claims.json: ≥150 records
```

**AC-1, AC-2, AC-3, AC-5**

---

### 2. Financial consistency spot-check

```bash
python -c "
import json, pathlib
claims = json.loads(pathlib.Path('data/claims.json').read_text())
errors = []
for c in claims:
    t = c['totals']
    if round(t['member_liability'] + t['payer_liability'], 2) != round(t['allowed_amount'], 2):
        errors.append(c['claim_id'])
print('Errors:', errors or 'None — all claims balance')
"
```

Expected: `Errors: None — all claims balance`

**AC-6**

---

### 3. Accumulator reconciliation spot-check

```bash
python -c "
import json, pathlib, collections
members = {m['member_id']: m for m in json.loads(pathlib.Path('data/members.json').read_text())}
claims  = json.loads(pathlib.Path('data/claims.json').read_text())
paid_by_member = collections.defaultdict(float)
for c in claims:
    if c['status'] == 'PAID':
        paid_by_member[c['member_id']] += c['totals']['member_liability']
errors = []
for mid, total in paid_by_member.items():
    acc = members[mid]['accumulators']
    recorded = acc['individual_deductible']['used'] + acc['individual_oop_max']['used']
    if abs(recorded - round(total, 2)) > 0.01:
        errors.append((mid, total, recorded))
print('Errors:', errors or 'None — accumulators reconcile')
"
```

Expected: `Errors: None — accumulators reconcile`

**AC-8**

---

### 4. Met flag spot-check

```bash
python -c "
import json, pathlib
members = json.loads(pathlib.Path('data/members.json').read_text())
errors = []
for m in members:
    for key in ['individual_deductible', 'individual_oop_max']:
        a = m['accumulators'][key]
        expected_met = a['used'] >= a['limit']
        if a['met'] != expected_met:
            errors.append((m['member_id'], key))
print('Errors:', errors or 'None — met flags correct')
"
```

Expected: `Errors: None — met flags correct`

**AC-4**

---

### 5. Cross-reference integrity

```bash
python -c "
import json, pathlib
members = {m['member_id'] for m in json.loads(pathlib.Path('data/members.json').read_text())}
fee_sched = {f['procedure_code'] for f in json.loads(pathlib.Path('data/fee_schedules.json').read_text())}
claims = json.loads(pathlib.Path('data/claims.json').read_text())
bad_member = [c['claim_id'] for c in claims if c['member_id'] not in members]
bad_code   = [c['claim_id'] for c in claims if c['line_detail'][0]['procedure_code'] not in fee_sched]
print('Bad member refs:', bad_member or 'None')
print('Bad procedure codes:', bad_code or 'None')
"
```

Expected: `Bad member refs: None` and `Bad procedure codes: None`

**AC-10, AC-11**

---

## Run integration tests

```bash
cd scripts
pip install pytest   # one-time; no other dependencies
pytest tests/test_seed_data.py -v
```

All tests should pass. The test suite covers all 13 acceptance criteria plus reproducibility.

---

## Load into Data Service

After generating seed data, start the Data Service to confirm the files load cleanly:

```bash
cd data_service
uvicorn main:app --port 8083
```

Expected startup log:
```
INFO: Data Service starting on port 8083
INFO: Loaded members=200, plans=5, fee_schedules=25, claims=≥150
```

Then verify the health endpoint:

```bash
curl http://localhost:8083/health
```

Expected:
```json
{ "status": "UP", "members": 200, "plans": 5, "fee_schedules": 25, "claims": 153 }
```

This also completes T027 from `specs/005-data-service/tasks.md` (quickstart validation with real seed data).
