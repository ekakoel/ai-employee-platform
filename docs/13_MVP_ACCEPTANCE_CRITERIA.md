# MVP Acceptance Criteria

## Product MVP

A company can:

- create/hire an AI Agent from a template;
- configure the Agent;
- assign knowledge;
- assign skills;
- assign tools;
- assign human users;
- assign a human supervisor;
- define approval behavior;
- use the Agent for tasks;
- consult the Agent;
- review approvals;
- inspect audit history.

## Human permissions

A normal employee:

- can use assigned AI;
- can create permitted tasks;
- can consult;
- cannot change Agent configuration without permission.

An authorized AI manager:

- can configure assigned AI;
- can manage skills/tools;
- can manage applicable policies;
- can review performance.

## AI execution

The system must:

- execute automatic actions;
- stop for approval-required actions;
- deny prohibited actions;
- never bypass backend authorization.

## Collaboration

An AI Agent can:

- recognize an outside-scope request;
- identify an appropriate Agent;
- delegate a structured task;
- receive the result;
- return the result to the requester.

## Learning

The system can:

- record task outcomes;
- record human corrections;
- create experience candidates;
- validate experiences;
- retrieve validated experiences later.

## Security

The system must guarantee:

- tenant isolation;
- permission enforcement;
- policy enforcement;
- approval enforcement;
- auditability;
- no direct LLM access to protected resources.

## Quality

Required before production:

- complete automated regression;
- security tests;
- integration tests;
- failure-path tests;
- documented operational behavior.
