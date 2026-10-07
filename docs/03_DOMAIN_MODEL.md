# AI Employee Platform — Domain Model

## Core entities

### Company

Tenant boundary.

Responsibilities:

- owns employees;
- owns AI Agents;
- owns knowledge;
- owns policies;
- owns tools/configuration;
- owns tasks and organizational memory.

### HumanUser / Employee

A human member of a company.

Attributes conceptually include:

- identity;
- department;
- role;
- status;
- permissions;
- AI access;
- approval authority.

### AI Agent Template

Reusable professional definition.

Contains:

- role;
- scope;
- responsibilities;
- default skills;
- default tools;
- default policies;
- evaluation criteria.

### AI Agent Instance

A company-specific AI Employee created from a template.

Contains:

- identity;
- company;
- template;
- role;
- scope;
- instructions;
- skills;
- tools;
- knowledge access;
- policies;
- autonomy;
- human supervisor;
- authorized users;
- status.

### Skill

A reusable unit of professional capability.

A skill may define:

- objective;
- instructions;
- required knowledge;
- allowed tools;
- workflow;
- evaluation criteria.

### Knowledge

Company or Agent-scoped information used by an Agent.

### Tool

A controlled capability that can perform an external or internal action.

### Policy

Rules governing whether an action is:

- allowed automatically;
- approval-required;
- denied.

### Approval

Human authorization record for a restricted action.

### Task

A unit of work requested from an Agent.

### Agent Message / Delegation

Structured communication between Agents or between humans and Agents.

### Experience

A validated record of a problem, approach, result and lesson.

### Memory

Reusable contextual information available to an Agent.

### Audit Event

Immutable trace of important operations.

## Conceptual relationships

```text
Company
  |
  +-- HumanUser
  |
  +-- AI Agent Instance
  |      |
  |      +-- Agent Template
  |      +-- Skills
  |      +-- Knowledge
  |      +-- Tools
  |      +-- Policies
  |      +-- Experience
  |
  +-- Tasks
  +-- Approvals
  +-- Audit Events
```

## Human access model

```text
Human
  |
  +-- AI Usage Permission
  |
  +-- AI Management Permission
  |
  +-- Approval Authority
```

These are separate concerns.

## AI access model

```text
AI Agent
  |
  +-- Scope
  +-- Capability
  +-- Tool Permission
  +-- Policy
  +-- Approval Policy
```

## Important invariants

1. Every Agent Instance belongs to exactly one company.
2. Every task is company-scoped.
3. Agent Context cannot load another company's knowledge.
4. A tool cannot execute without backend authorization.
5. Approval execution uses the stored approval as source of truth.
6. An Agent cannot bypass ToolExecutor.
7. An Agent cannot change its own permissions.
8. Experience cannot silently become policy.
