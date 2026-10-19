# Feature: Inventory (availability)

## Purpose
Store durable product/hotel availability for the company. AI tool `search_availability` reads this during **task execute**.

## Who
| Role | View list | Seed / hydrate / playbook |
|------|-----------|---------------------------|
| Owner / AI Admin | Yes | Yes |
| Manager | Yes | If has manage/write |
| Reservation / Member | Yes (read) | No (actions hidden) |

## Frontend
- Nav **Inventory**
- List + stats
- Actions card: Seed demo, Demo playbook, Hydrate (gated)

## Backend
- `GET /companies/{id}/inventory`
- `POST /companies/{id}/demo/seed-reservation`
- `POST /companies/{id}/demo/playbook-reservation`
- `POST /companies/{id}/inventory/hydrate`

## Flow
1. Seed (or load real inventory later)
2. Hire reservation AI Employee + grant access
3. Task **execute**: “check availability Alila…”
4. Policy / Approvals if booking tools run
