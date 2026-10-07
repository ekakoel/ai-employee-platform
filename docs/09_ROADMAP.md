# AI Employee Platform — Development Roadmap

## Roadmap philosophy

Build the smallest secure vertical slice first, then expand capability.

Do not implement SaaS-scale complexity before the underlying domain and runtime are proven.

## Phase 0 — Foundation

Status: substantially complete.

- repository structure;
- company/tenant model;
- users/roles/permissions foundation;
- Agent Catalog;
- Agent Subscription;
- Agent Instance;
- Knowledge;
- Tasks;
- audit;
- policy/approval foundation.

## Phase 1 — Secure AI Runtime

Status: core foundation complete; integration verification completed in the latest session.

- LLM provider abstraction;
- Ollama provider;
- Agent Runtime;
- tool schema/registry;
- Tool Executor;
- policy boundary;
- approval lifecycle;
- LLM tool calling;
- approval resume/rejection;
- regression suite.

Latest verified result: **69 passed, 1 warning**.

## Phase 2 — Agent Template System

Goal:

```text
Template
 ↓
Create/Hire Agent
 ↓
Configured Agent Instance
```

Work:

- Agent Template model;
- template versioning;
- default skills;
- default tools;
- default policy recommendations;
- default autonomy;
- template catalog API;
- template administration.

## Phase 3 — Human Employee + AI Access

Work:

- human employee model refinement;
- AI access assignment;
- AI supervisor assignment;
- AI management permissions;
- approval authority;
- employee-to-agent many-to-many access;
- UI/API authorization.

## Phase 4 — Skills

Work:

- Skill entity;
- skill catalog;
- Agent-skill assignment;
- company custom skills;
- skill instructions;
- required tools;
- evaluation criteria;
- skill versioning.

## Phase 5 — Configurable Policy / Approval

Work:

- policy rule model;
- AUTO / APPROVAL / DENY;
- conditional rules;
- amount/risk conditions;
- approval levels;
- approval routing;
- policy simulation/testing;
- audit trail.

## Phase 6 — Knowledge + Memory

Work:

- document ingestion;
- extraction;
- chunking;
- semantic retrieval;
- company/Agent scoping;
- Agent memory;
- memory lifecycle;
- retention controls.

Infrastructure choices such as PostgreSQL/pgvector/object storage should be introduced based on tested requirements.

## Phase 7 — Experience Learning

Work:

- experience candidate;
- evaluation;
- human feedback;
- validation;
- experience retrieval;
- confidence;
- learning dashboard.

## Phase 8 — Human/AI Workspace

Work:

- AI inbox;
- task center;
- approvals;
- Agent chat;
- consultation mode;
- Agent status;
- notifications;
- AI workforce dashboard.

## Phase 9 — AI Directory + Delegation

Work:

- capability registry;
- Agent directory;
- structured Agent messages;
- delegation;
- result propagation;
- timeout/retry;
- escalation;
- collaboration audit.

## Phase 10 — Automation

Work:

- triggers;
- schedules;
- event-driven tasks;
- recurring tasks;
- workflow execution;
- automation monitoring;
- safe retry/idempotency.

## Phase 11 — Performance / Governance

Work:

- Agent performance;
- task metrics;
- approval latency;
- human correction;
- experience quality;
- cost/usage;
- audit analytics;
- governance dashboards.

## Phase 12 — SaaS Production

Work:

- authentication;
- organization management;
- PostgreSQL production migration;
- background workers;
- object storage;
- production deployment;
- observability;
- billing/subscription;
- quotas;
- plan limits;
- support/admin tools.

## Phase 13 — Integrations

Only after the core platform is stable:

- email;
- CRM;
- calendar;
- accounting systems;
- messaging;
- external APIs;
- company-specific connectors.

## Phase 14 — Marketplace / Ecosystem

Future:

- Agent templates marketplace;
- skill marketplace;
- tool marketplace;
- company custom Agent packages;
- partner ecosystem.

## Phase gates

Every phase requires:

1. domain design;
2. security review;
3. implementation;
4. unit/integration tests;
5. regression;
6. documentation;
7. acceptance criteria;
8. only then phase completion.
