# Feature: Users, invitations & job positions

## Purpose
Owner adds employees and assigns a **job position** (company role).

## Frontend
- Nav: **Users & Roles**
- Invite: email + **Job position** dropdown
- List employees with position selector + **Save position**
- Pending invitations with role and revoke

## Job positions (company roles)
| Role | Typical use |
|------|-------------|
| `member` | General employee |
| `reservation` | Reservation staff |
| `manager` | Supervisor |
| `ai_admin` | AI Administrator (agents, skills, knowledge) |
| `contract_manager` | Contracts / documents |
| `administration` | Admin staff |
| `accounting` | Accounting |
| `owner` | Company owner — **not** assignable via invite |

## Backend
- `GET /api/v1/companies/{id}/job-roles`
- `POST /api/v1/companies/{id}/invitations` `{ email, role_name }`
- `GET /api/v1/companies/{id}/invitations`
- `POST /api/v1/companies/{id}/invitations/{id}/revoke`
- `PUT /api/v1/companies/{id}/users/{user_id}/role` `{ role_name }`
- Accept invite: `POST /api/v1/auth/accept-invitation`

## Accept invitation (frontend)
- Tab: **Accept invitation**
- Token (from email or debug field) + name + password

## Rules
- Only owner invites after onboarding is complete
- Changing role revokes that user’s sessions (re-login required)
- Direct `POST .../users` create is disabled (410)
