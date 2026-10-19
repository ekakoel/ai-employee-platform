# Feature: Advisory chat

## Purpose
Staff talk to a hired AI Employee using **company knowledge**. Chat does **not** run tools (no bookings, no inventory writes).

## Who
Requires `agent.read` and an agent with `can_use` (or owner/ai_admin).  
**Also create Task** requires `task.create`.

## Frontend
- Nav **Chat**
- Pick AI Employee → new or existing conversation
- Spinner while waiting for reply
- Optional **Also create Task** (consult or execute mode) → **Run task now** / **Tasks**

## Flow
1. Hire AI Employee + grant access  
2. Add knowledge (contracts, SOPs)  
3. Chat for advice  
4. Tick create Task when action is needed → run under policy → **Results** / **Approvals** if required  

## Backend
- `POST /companies/{id}/conversations`
- `POST /companies/{id}/conversations/{id}/messages` `{ content, create_task, task_mode }`
- Task execute/consult endpoints under Tasks
