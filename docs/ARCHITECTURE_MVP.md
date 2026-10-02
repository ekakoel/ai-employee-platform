# AI Employee Platform — Local MVP Architecture

## Phase 0.1
Implemented:
- Company
- Agent Catalog
- Agent Instance / hiring
- Company-scoped Knowledge CRUD
- Company-scoped Tasks
- Agent ownership boundary

## Phase 0.2
Implemented:
- Company Users
- Built-in roles: owner, manager, member
- Permission model
- Tenant-bound user access
- Audit log for important mutations
- Development identity via `X-User-ID` header

The `X-User-ID` header is deliberately a local development identity mechanism, not production authentication.

## Security rule
A request to a company-scoped endpoint must satisfy:

1. User exists and is active.
2. User belongs to the requested company.
3. User's role has the required permission.
4. Agent resources belong to the requested company.

## Important boundary
The Agent Catalog defines platform capabilities. An Agent Instance is the company-owned operational instance created when the company hires/subscribes to an Agent Catalog item.

The LLM is not yet part of this phase. Business execution will later pass through:

`User -> Company -> Agent Instance -> Task -> Runtime -> Policy/Permission -> Tool -> External System`


## Phase 0.3
Implemented:
- Agent Subscription entity between Agent Catalog and Agent Instance.
- Company-scoped subscription listing.
- Subscription cancellation lifecycle.
- Cancellation automatically deactivates associated Agent Instances.
- Inactive/cancelled Agents cannot receive new Tasks.
- Audit events for hire and subscription cancellation.

## Product model
The intended model is:

`Agent Catalog -> Agent Subscription -> Agent Instance`

- **Agent Catalog**: platform-defined AI Employee product/type.
- **Agent Subscription**: company's entitlement to use that Agent type.
- **Agent Instance**: operational AI Employee instance belonging to the company.

A company can only execute work through active Agent Instances backed by an active subscription owned by the same company.
