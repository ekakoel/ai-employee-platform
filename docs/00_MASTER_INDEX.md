# AI Employee Platform — Master Documentation Index

**Project:** AI Employee Platform  
**Repository:** `ekakoel/ai-employee-platform`  
**Primary branch:** `development`  
**Document baseline:** 2026-10-06

## Purpose

This documentation set is the long-term product and engineering reference for the AI Employee Platform.

It defines:

- product vision and positioning;
- human + AI organizational model;
- AI Agent Template model;
- Agent configuration and lifecycle;
- skills, knowledge, tools, memory and experience;
- permissions, autonomy and approval;
- human-to-AI and AI-to-AI collaboration;
- security and tenant isolation;
- roadmap;
- developer joblist;
- testing and release gates;
- documentation governance.

## Document map

1. `01_PRODUCT_BLUEPRINT.md` — complete product concept.
2. `02_PRODUCT_PRINCIPLES.md` — non-negotiable product principles.
3. `03_DOMAIN_MODEL.md` — business/domain entities and relationships.
4. `04_ARCHITECTURE_BLUEPRINT.md` — technical architecture and runtime boundaries.
5. `05_AI_AGENT_TEMPLATE_SPEC.md` — standard/default AI Agent templates.
6. `06_PERMISSION_APPROVAL_AUTONOMY.md` — permissions, approval, autonomy and authorization.
7. `07_HUMAN_AI_COLLABORATION.md` — human/AI/AI-to-AI collaboration model.
8. `08_MEMORY_EXPERIENCE_LEARNING.md` — controlled memory and learning from experience.
9. `09_ROADMAP.md` — phased implementation roadmap.
10. `10_DEVELOPER_JOBLIST.md` — actionable developer worklist.
11. `11_TESTING_QUALITY_SECURITY.md` — quality, security and acceptance gates.
12. `12_DOCUMENTATION_GOVERNANCE.md` — how the project documentation must evolve.
13. `13_MVP_ACCEPTANCE_CRITERIA.md` — product and technical acceptance criteria.

## Current implementation baseline

The repository already contains the core runtime/security foundation:

- Company-aware Agent Context;
- Agent Runtime;
- LLM provider abstraction/factory;
- Tool Registry;
- Tool Executor;
- Policy Engine;
- Approval lifecycle;
- deterministic task execution;
- LLM task execution path;
- approval propagation and resume lifecycle;
- regression coverage.

The latest verified project session reported **69 tests passing with 1 existing Starlette/httpx deprecation warning**.

The dated `docs/SESSION_HANDOFF_5AL.md` may contain an earlier intermediate 5AL state. When it conflicts with the latest verified session result, the latest audited repository/test state is authoritative.

## Source-of-truth rules

1. Code is authoritative for implemented behavior.
2. Tests are authoritative for verified behavior.
3. Architecture documents describe intended boundaries.
4. Roadmaps describe planned work, not completed work.
5. Do not mark roadmap items complete without implementation and tests.
6. Product ideas may be added, changed or removed as the product is validated.
