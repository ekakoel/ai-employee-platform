# AI Employee Platform — 15-minute demo script

**Audience:** stakeholders / first-time testers  
**Password for all demo users:** `demo12345`

## Before you start

1. Start API: `uvicorn app.main:app --reload`
2. Open workspace: `http://127.0.0.1:8000/workspace`
3. Optional LLM: `ollama serve` (chat works advisory without tools)

---

## A. Bootstrap (2 min)

1. On `/developer` login gate (DEBUG), open **Quick start** — uses `POST /api/v1/demo/bootstrap`.
   Production: **Register company** → verify email → complete Company profile.
2. Note demo accounts in the log:
   - `owner@demo.local` — full company control
   - `reservation@demo.local` — front desk / chat & tasks
   - `contracts@demo.local` — knowledge upload
   - `aiadmin@demo.local`, `manager@demo.local`, `admin@demo.local`
3. Login as **owner@demo.local** / `demo12345`.

---

## B. Demo readiness (1 min)

1. Open **Home**.
2. Look at **Demo readiness**:
   - Required: AI employee + inventory
   - If red → click **Run demo playbook**
3. When green: “Workspace is demo-ready”.

---

## C. Reservation playbook (5 min)

1. **Run demo playbook** (Home or Inventory).
2. You land on **Tasks** with a pending execute task (Alila availability).
3. Click **Run execute** (not chat-only).
4. Open **Results** / task result — availability rates for Alila-style rooms.
5. Explain: *Chat is advisory; tools run only on Tasks under policy.*

---

## D. Contract knowledge (4 min)

1. Login as **contracts@demo.local** (or stay owner).
2. Open **Knowledge**.
3. Upload a small `.txt` or PDF contract → **Extract to knowledge**.
4. Confirm badge **from extract** and filter **From document extract**.
5. Emphasize: *file bytes are discarded; only text stays in the DB.*

---

## E. Role gating (2 min)

1. Login as **reservation@demo.local**.
2. Show Chat / Tasks / limited nav (no Users admin).
3. Login as **admin@demo.local** — Users / usage style surfaces.
4. Platform **developer** console is `/developer` (not a company role).

---

## F. Optional smoke (API)

```powershell
pytest tests/test_smoke_e2e_job54.py -q
```

Covers: playbook → execute → knowledge ingest → inventory list.

---

## Talking points

| Point | Message |
|-------|---------|
| Human-in-the-loop | Approvals gate irreversible actions |
| Policy | Tools denied by default until allow rules |
| Multi-role | Owner / reservation / contract_manager / admin |
| Storage | Knowledge extract without keeping files |
| Developer | Skill catalog upgrades = platform only |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Demo readiness red | Run playbook; hire agent |
| Execute denied by policy | Playbook seeds demo policies; re-run seed/playbook |
| Chat refuses tools | Expected — create Task / Run execute |
| Login fails | Use Quick start emails + `demo12345` |
| Ollama errors | Chat still advisory; execute uses tools/mock path |
