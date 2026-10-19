# Feature: AI Administrator

## Purpose
Owner appoints a company user who can manage the AI workforce (agents, skills, knowledge, policies) without transferring ownership.

## Frontend
- **Users & Roles**: button **Make AI administrator** / **Remove AI admin**
- Or set job position to **AI Administrator** and save

## Backend
- `PUT /api/v1/companies/{id}/administrators/{user_id}` `{ "administrator": true|false }`
- Equivalent to role `ai_admin` vs `member` (legacy helper)
- Prefer explicit job position API for other roles

## Rules
- Only owner can appoint/revoke
- Cannot change the owner account this way
- Role change invalidates active sessions
