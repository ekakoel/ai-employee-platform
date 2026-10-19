# Job 60 — Debug demo bootstrap (fix Quick start)

**Date:** 2026-10-19  
**Patch:** `job60_demo_bootstrap.patch`

## Why
After Phase 2 auth hardening:
- `POST /companies` requires platform admin
- `POST /companies/{id}/users` returns **410** (invitations only)

Legacy **Quick start** still called those endpoints → `Authentication required` / failure.

## Solution
| Piece | Detail |
|-------|--------|
| `POST /api/v1/demo/bootstrap` | Debug-only (`DEBUG=true`) |
| Creates | Company (`onboarding_status=complete`) + verified personas + optional agents |
| Returns | emails, password `demo12345`, company id |
| Quick start UI | Calls bootstrap → auto `/auth/login` → workspace |

**Not for production.** Production path remains: Register company → verify email → profile → invitations.

## Apply
```powershell
git pull origin development
git apply job60_demo_bootstrap.patch
pytest tests/test_demo_bootstrap_job60.py -q
# Ensure .env has DEBUG=true for local demo
uvicorn app.main:app --reload
# Open /developer → Quick start
```
