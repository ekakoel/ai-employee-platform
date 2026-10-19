# Product walkthrough — official UI path

**Goal:** exercise the full company path **without** relying on Quick start (optional for developers only).

**Time:** ~20–30 minutes first time; ~15 minutes once familiar.

## Prerequisites
- API running: `uvicorn app.main:app --reload`
- Browser: `http://127.0.0.1:8000/workspace`
- Email: in `DEBUG` / `APP_ENV=development`, verification & invite tokens appear in the UI

---

## Phase 1 — Company & people

| Step | Where | Action |
|------|--------|--------|
| 1 | Register company | Create business; you become **Owner** |
| 2 | Verify email | Paste debug token if shown |
| 3 | Sign in | Email + password only |
| 4 | Company profile | Name, contact email, industry → **Save** (unlocks sidebar) |
| 5 | Users & positions | Invite AI Administrator + Reservation (job position dropdown) |
| 6 | Accept invitation | Login gate → Accept invitation → staff sign in |

Docs: [01](01_company_registration.md)–[05](05_ai_administrator.md)

---

## Phase 2 — AI workforce & data

| Step | Where | Action |
|------|--------|--------|
| 7 | AI Employees | Hire from catalog; grant `can_use` to reservation staff |
| 8 | Knowledge | Extract PDF/DOCX/TXT or add notes |
| 9 | Inventory | Seed reservation demo (or load real rates later) |

Docs: [06](06_ai_employees_hire.md)–[07](07_knowledge.md), [11](11_inventory.md)

---

## Phase 3 — Work

| Step | Where | Action |
|------|--------|--------|
| 10 | Home | Role quick actions + needs attention |
| 11 | Chat | Advisory only; optional “Also create Task” |
| 12 | Tasks | Consult or Execute |
| 13 | Approvals | Manager/Owner approve restricted tools |
| 14 | Inbox / Notifications | Track open work and alerts |

Docs: [08](08_chat.md)–[10](10_approvals.md), [12](12_home_inbox.md), [13](13_notifications.md)

---

## Phase 4 — Role checks (optional)

1. Login as **Reservation** — Chat/Tasks/Inventory visible; Users/Hire hidden  
2. Login as **AI Admin** — Hire + invite operational staff; cannot appoint another AI Admin  
3. Login as **Manager** — Approvals approve/reject  

---

## Developer-only shortcuts
- `/developer` + **Quick start** → `POST /api/v1/demo/bootstrap` (DEBUG)
- Demo playbook on Home/Inventory seeds inventory + sample task  

See also: [DEMO_15MIN.md](../DEMO_15MIN.md)
