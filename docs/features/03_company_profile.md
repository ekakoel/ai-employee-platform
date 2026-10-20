# Feature: Company profile

## Purpose
Organization identity (name, contact email, industry) and onboarding gate for the workspace sidebar.

## API
| Method | Path | Who |
|--------|------|-----|
| GET | `/api/v1/companies/{id}/profile` | Any company user |
| PUT | `/api/v1/companies/{id}/profile` | **Owner only** |

## UI (role matrix)

| Role | View | Edit form / Save |
|------|------|------------------|
| Owner | Full + onboarding checklist until complete | Yes |
| AI Admin, Administration, Manager, Reservation, Contract, Accounting, Member | Read-only summary | No — form hidden |

## Frontend
- `#companyProfileEdit` — owner only
- `#companyProfileRead` — non-owner only
- `applyCompanyProfileMode()` in `app.js`

## Flow
```
Owner: register → verify → login → complete profile → sidebar unlock → invite staff
Staff: login → see read-only company profile (no edit controls)
```
