# Testing, Quality and Security Strategy

## Test layers

### Unit tests

Test isolated:

- policy evaluation;
- permission evaluation;
- scope matching;
- parsers;
- template inheritance;
- experience ranking.

### Integration tests

Test:

- Agent Runtime + Tool Executor;
- policy + approval;
- task lifecycle;
- knowledge isolation;
- delegation.

### API tests

Test:

- authentication/authorization;
- company isolation;
- human AI permissions;
- approval endpoints;
- Agent management.

### End-to-end tests

Critical scenarios:

1. Human gives task → AI executes automatic action.
2. Human gives task → AI requests approval.
3. Human approves → action executes.
4. Human rejects → action never executes.
5. AI receives outside-scope request → delegates.
6. Delegated Agent returns result.
7. Human asks AI for consultation → recommendation only.
8. AI uses validated past experience.
9. Unauthorized employee cannot manage AI.
10. Cross-company access is impossible.

## Security invariants

Never allow:

```text
LLM -> database
LLM -> unrestricted API
Agent A -> Agent B database
Approval -> arbitrary replacement arguments
Human user -> policy bypass
Experience -> permission change
```

## Regression policy

Every security-sensitive change must include a regression test.

## Performance tests

Later phases should measure:

- task latency;
- LLM latency;
- tool latency;
- delegation latency;
- approval waiting time;
- queue throughput.

## Failure handling

AI tasks must support explicit failure states.

Avoid silently retrying actions that may have side effects.

Use idempotency for external operations.

## Audit requirements

Audit:

- Agent creation;
- Agent configuration;
- permission changes;
- policy changes;
- approval decisions;
- tool execution;
- delegation;
- escalations;
- experience validation;
- human corrections.

## Release gates

A release should not proceed if:

- security tests fail;
- tenant isolation fails;
- approval bypass exists;
- deterministic regression fails;
- critical documentation is missing.
