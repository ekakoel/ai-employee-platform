# AI Agent Template Specification

## Purpose

Templates provide standardized, reusable AI Employees for common professional roles.

A template is a starting point, not a rigid behavior lock.

## Template structure

```text
Template
├── Identity
├── Role
├── Scope
├── Responsibilities
├── Default Skills
├── Default Tools
├── Default Knowledge Requirements
├── Default Policies
├── Default Approval Recommendations
├── Default Autonomy
├── Evaluation Criteria
└── Version
```

## Reservation AI

### Responsibilities

- process inquiries;
- prepare quotations;
- prepare itineraries;
- check reservation information;
- follow up customers;
- prepare reservation reports;
- escalate unusual cases.

### Default skills

- quotation preparation;
- itinerary planning;
- reservation management;
- customer communication;
- follow-up;
- reporting.

### Default policy recommendations

- draft quotation: automatic;
- quotation calculation: automatic;
- send quotation: approval by default;
- unusual discount: approval;
- booking confirmation: approval where business policy requires it.

## Accounting AI

### Responsibilities

- prepare financial reports;
- prepare invoice drafts;
- analyze transaction data;
- track payment status;
- prepare expense/revenue reports;
- identify anomalies for human review.

### Default skills

- invoice preparation;
- revenue reporting;
- expense analysis;
- payment tracking;
- financial reporting.

### Default policy recommendations

- generate report: automatic;
- prepare invoice draft: automatic;
- send invoice: company-configurable;
- payment execution: approval;
- refund: approval.

## Sales AI

### Responsibilities

- qualify leads;
- prepare proposals;
- follow up leads;
- summarize sales activity;
- recommend next actions.

## Customer Service AI

### Responsibilities

- answer approved FAQs;
- classify inquiries;
- prepare responses;
- escalate complex cases;
- summarize customer history.

## Operations AI

### Responsibilities

- prepare operational tasks;
- coordinate approved workflows;
- monitor execution status;
- prepare supplier/operations reports;
- escalate exceptions.

## Template versioning

Templates must be versioned.

Changing a template must not silently alter already deployed Agent Instances.

Future model:

```text
Template v1
Template v2
Template v3
```

An existing Agent may:

- stay on current version;
- upgrade manually;
- upgrade after controlled migration.

## Company customization

A company can customize:

- instructions;
- skills;
- tools;
- knowledge;
- policies;
- approval rules;
- autonomy;
- supervisor;
- users.

Company customization must remain tenant-scoped.
