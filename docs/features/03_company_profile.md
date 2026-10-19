# Feature: Company profile (complete onboarding)

## Purpose
Owner fills organization details so the workspace unlocks.

## Frontend
- Nav: **Company profile** (forced landing while status is pending)
- Fields: name, contact email, industry
- Save → `onboarding_status=complete`

## Backend
- `GET /api/v1/companies/{id}/profile`
- `PUT /api/v1/companies/{id}/profile`

## Rules
- Only **owner** may complete profile
- While pending, most workspace routes return 403
- `/auth/me` and profile remain available

## Next
[Users, invitations & job positions](04_users_roles_employees.md)
