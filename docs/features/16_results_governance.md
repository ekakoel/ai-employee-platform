# Feature: Results, Governance & Usage

## Results (Output center)
Structured outputs from **Task execute**: quotations, availability, reservations.

Chat advisory mode does not write tool results here.

## Governance
Owner overview (`governance.read`): agents, recent audit. Day-to-day gates: Approvals / Inbox.

## Plan & usage
Quota consumption (`usage.read`).

## Flow
```
Task execute → (approval) → Results → Governance/Audit
```
