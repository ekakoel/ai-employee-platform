# Feature: Register business (company)

## Purpose
Create a new tenant (company) and the first human user as **Owner**.

## Who uses it
Anyone starting a new organization on the platform (public registration).  
**Not** used by existing employees (they use invitation).

## Frontend
- URL: `/workspace`
- Tab: **Register company**
- Fields: company name, owner name, owner email, password

## Backend
- `POST /api/v1/auth/register`
- Body: `company_name`, `owner_name`, `email`, `password`
- Does **not** return a session token
- Owner role is assigned server-side

## Outcome
- Company created with `onboarding_status=pending`
- Owner user created, email **unverified** until verification step
- Next: [02_email_verification.md](02_email_verification.md)

## Rules
- Email and company name must be unique
- Platform admin is never granted via registration
- Production may require SMTP; in `DEBUG` a verification token is returned for local use
