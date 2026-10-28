# bank-transfer (Project Defense demo app)

A small wallet API split into routes (`app/main.py`), a ledger service (`app/ledger.py`), a fraud-scoring
client (`app/fraud.py`) and an in-memory store (`app/store.py`). Ten accounts start with $100,000 each, so
an attack can't drain them and every lost update shows up as missing money.

- `flaws.json`: the ground truth (one critical race in `ledger.transfer` across the fraud-check await).
- `reference_attack.json`: the backup attack (fan-in transfers into one account).
- `fixed/`: the reference fix (one ledger lock around read → check → write).

Built from `backend/tests/fixtures/apps/bank-transfer-min` for IC1 (PLAN §11.2, DATA-4).
