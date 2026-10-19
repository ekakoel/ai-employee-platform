# Feature: Tasks (consult / execute)

## Purpose
Policy-gated work items where the AI Employee may use tools. Separate from advisory chat.

## Modes
| Mode | Behavior |
|------|----------|
| **Consult** | Plan / analysis only (safer) |
| **Execute** | Tools run; may create approval requests |

## Who
- Create: `task.create` (Owner, AI Admin, Manager, Reservation, Member, …)
- Read list: `task.read`
- Run consult/execute: same company + agent access

## Frontend
- **Tasks** — create form (hidden without `task.create`) + task center with Consult / Execute actions
- Linked from Chat “Also create Task”

## Backend
- `POST /companies/{id}/tasks`
- `POST /companies/{id}/tasks/{id}/consult`
- `POST /companies/{id}/tasks/{id}/execute`
