# Feature: Email verification

## Purpose
Prove control of the owner (or user) email before sign-in.

## Frontend
- After registration, **Verification token** panel appears (debug)
- Button: **Verify email**
- Link recovery: **Request verification again**

## Backend
- `POST /api/v1/auth/verify-email` `{ "token": "..." }`
- `POST /api/v1/auth/request-verification` `{ "email": "..." }`

## Outcome
- `email_verified=true`
- User can sign in with email + password
- Next: complete [company profile](03_company_profile.md)
