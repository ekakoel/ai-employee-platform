# Feature: Approvals

## Purpose
Human gate for restricted tool actions (e.g. create_reservation). Approve continues the task; reject stops it.

## Who
- View: `approval.read`
- Approve/Reject: `approval.manage` (Owner, Manager typically)
- Other roles see pending items as read-only “waiting for manager”

## Frontend
- **Approvals** nav + Inbox badges
- Approve / Reject buttons only with `approval.manage`

## Backend
- `GET /companies/{id}/approvals`
- `POST /companies/{id}/approvals/{id}/approve`
- `POST /companies/{id}/approvals/{id}/reject`
