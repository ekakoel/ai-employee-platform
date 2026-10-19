# Feature: Hire AI Employees

## Purpose
Owner and AI Administrator hire AI Employee instances from the platform catalog for the company.

## Who
| Role | Hire | Grant staff access | Use agent (chat/task) |
|------|------|--------------------|------------------------|
| Owner | Yes | Yes | Yes |
| AI Administrator | Yes | Yes | Yes |
| Manager | No* | Yes if `agent.manage` | Yes |
| Reservation / Member | No | No | After `can_use` grant |

\* Manager has `agent.hire` in matrix — may hire; UI shows Hire when `agent.hire` or `agent.manage` is present.

## Frontend
- Nav: **AI Employees** (requires `agent.read`)
- Card **Hire AI Employee** (hidden without `agent.hire` / `agent.manage`)
- List hired instances
- **Agent access** — grant `can_use` to operational users

## Backend
- `GET /api/v1/agent-catalog`
- `POST /api/v1/companies/{id}/agents/{catalog_id}/hire` `{ "name": "..." }`
- `GET /api/v1/companies/{id}/agents`
- Grant access endpoints under agent access

## After hire
1. Staff with operational roles need **Grant can_use** (or Grant all operational users)
2. Chat is advisory; Task execute uses tools under policy
