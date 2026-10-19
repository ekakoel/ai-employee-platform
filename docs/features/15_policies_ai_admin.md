# Feature: Policies (AI Administrator)

## Purpose
Rules for tools during **Task execute**:

| Effect | Meaning |
|--------|---------|
| `allow` | Tool runs without human gate |
| `require_approval` | Approval queue |
| `deny` | Blocked |

**Default:** no matching policy → **denied**.

## Who
| Role | View | Create |
|------|------|--------|
| Owner | Yes | Yes |
| AI Administrator | Yes | Yes |
| Others | Usually no | No |

## Frontend
- Nav **Policies**
- Effects: allow / require_approval / deny
- Example tools: `search_availability`, `send_quotation`, `create_reservation`

## Starter policies (travel)
1. `search_availability` → allow  
2. `create_reservation` → require_approval  

## Backend
- `GET /companies/{id}/policies`
- `POST /companies/{id}/policies`
- Policy Simulator on developer console
