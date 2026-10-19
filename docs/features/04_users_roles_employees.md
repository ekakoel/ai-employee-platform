# Feature: Users, invitations & job positions

## Purpose
Owner adds employees and assigns a **job position**. Only the company **Owner** can invite or change positions.

## Frontend
- Nav: **Users & positions**
- Invite: email + job position → **Send invitation**
- Employee list: change position → **Save position**
- **Make AI administrator** shortcut
- Debug token when DEBUG=true → login gate **Accept invitation**

## Hierarchy
Owner → AI Administrator → Manager/Supervisor → operational roles (reservation, contract, accounting, administration, member)

## Backend
- `GET /companies/{id}/job-roles`
- `POST /companies/{id}/invitations` `{ email, role_name }`
- `PUT /companies/{id}/users/{id}/role` `{ role_name }`
- `POST /auth/accept-invitation`
