# Developer Joblist

## Developer operating rules

1. Audit existing source before modifying it.
2. Preserve working behavior.
3. Do not use speculative changes.
4. Do not bypass ToolExecutor.
5. Do not bypass PolicyEngine.
6. Do not bypass ApprovalService.
7. Do not move authorization into the LLM.
8. Preserve company isolation.
9. Do not use destructive DB commands.
10. Run tests after meaningful changes.
11. Prefer one concrete command/step at a time.
12. Do not request successful command output unless it is genuinely needed.
13. Use full-file replacement when a complete file replacement is safer and clearer.
14. Do not commit unless explicitly requested or the project workflow requires it.

## Immediate backlog

### Job 01 — Establish new product documentation

- Add the blueprint documents to repository docs.
- Add documentation index.
- Mark product vision as living specification.
- Keep implementation status separate from future vision.

### Job 02 — Audit domain model

Inspect current entities and identify gaps for:

- Agent Template;
- Human Employee;
- AI access assignment;
- AI supervisor;
- Skill;
- Policy rule;
- Approval authority;
- Agent capability;
- Agent delegation;
- Experience.

Do not implement all entities yet. Produce a gap report first.

### Job 03 — Design Agent Template

Deliver:

- schema;
- versioning;
- default skills;
- default tools;
- default policies;
- default autonomy;
- evaluation criteria.

Tests:

- template creation;
- version isolation;
- Agent creation from template;
- company isolation.

### Job 04 — Human AI Access

Deliver:

- AI user assignment;
- AI manager assignment;
- permission checks;
- approval authority.

Tests:

- normal employee can use;
- normal employee cannot configure;
- manager can configure assigned Agent;
- unauthorized employee denied.

### Job 05 — Skill system

Deliver:

- Skill model;
- catalog;
- Agent assignment;
- company custom skill;
- skill versioning.

Tests:

- skill access;
- tenant isolation;
- tool requirement enforcement.

### Job 06 — Policy rules

Deliver:

- rule model;
- evaluation;
- conditional conditions;
- AUTO/APPROVAL/DENY;
- approval routing.

Tests must include:

- low-risk automatic;
- approval required;
- denial;
- conditional amount;
- unauthorized approver.

### Job 07 — Agent consultation mode

Deliver:

- consultation task type;
- recommendation response;
- no-action guarantee unless explicitly requested;
- context/knowledge retrieval.

### Job 08 — Agent Directory

Deliver:

- capability registry;
- Agent discovery;
- structured delegation request;
- target Agent validation.

### Job 09 — Inter-agent execution

Deliver:

- delegation task;
- status;
- result propagation;
- failure;
- timeout;
- audit.

### Job 10 — Experience system

Deliver:

- experience candidate;
- validation;
- retrieval;
- confidence;
- feedback.

### Job 11 — Automation

Deliver:

- scheduled tasks;
- event triggers;
- safe retries;
- idempotency;
- approval pauses.

### Job 12 — Human workspace

Deliver:

- task center;
- approval center;
- AI inbox;
- Agent dashboard;
- workforce overview.

### Job 13 — Production infrastructure

Only after core product behavior is stable:

- authentication;
- PostgreSQL;
- migrations;
- object storage;
- workers;
- observability;
- production deployment.

## Definition of Done

A developer job is not complete until:

- implementation exists;
- tests exist;
- security boundary is verified;
- tenant isolation is verified;
- API/UI behavior is documented;
- regression suite passes;
- roadmap status is updated.

## Recommended issue format

```text
Title:
[AREA] Short action

Context:
Why this work is needed.

Scope:
What will change.

Out of scope:
What must not change.

Acceptance criteria:
- ...
- ...

Security:
- ...

Tests:
- ...

Dependencies:
- ...

Documentation:
- ...
```
