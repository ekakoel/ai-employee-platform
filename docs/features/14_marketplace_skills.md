# Feature: Marketplace & Skills

## Marketplace
Public AI Employee **templates**. **Install** copies skills into the company catalog; it does **not** create a running agent instance.

| Action | Who |
|--------|-----|
| Browse templates | Users with marketplace access |
| Install template | `agent.hire` or `agent.manage` (Owner, AI Admin) |
| Hire instance | **AI Employees** page after install |

### Backend
- `GET /api/v1/marketplace/templates`
- `POST /companies/{id}/marketplace/install/{catalog_id}`
- `GET /companies/{id}/marketplace/installations`

## Skills
| Action | Who |
|--------|-----|
| List skills | Company users with agent access |
| Create **company** skill | `agent.manage` (Owner, AI Admin) |
| Upgrade **platform** skill catalog | Platform developer only (`/developer`) |

### Backend
- `GET /companies/{id}/skills`
- `POST /companies/{id}/skills`

## Flow
```
Marketplace Install → AI Employees Hire → Chat/Tasks
```
