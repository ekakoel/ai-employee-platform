# Permissions, Approval, Autonomy and Authorization

## 1. Separate four concepts

### AI usage

Can the human use the AI?

### AI management

Can the human configure the AI?

### Business approval

Can the human approve a specific action?

### AI execution authority

Can the AI perform the action automatically?

These must not be conflated.

## 2. Human permission examples

```text
ai.use
ai.consult
ai.task.create
ai.view
ai.approve
ai.manage
ai.configure
ai.train
ai.assign
ai.manage_permissions
ai.manage_policies
```

## 3. Example employee

```text
Reservation Staff
- ai.use: yes
- ai.consult: yes
- ai.task.create: yes
- ai.approve: no
- ai.manage: no
- ai.configure: no
```

## 4. Example AI Supervisor

```text
AI Supervisor
- ai.use: yes
- ai.consult: yes
- ai.task.create: yes
- ai.approve: yes
- ai.manage: yes
- ai.configure: yes
- ai.train: yes
- ai.assign: yes
```

## 5. Approval policies

Policy outcomes:

```text
AUTO
APPROVAL
DENY
```

Conditional rules may use:

```text
action
amount
currency
risk
customer
department
requester
agent
destination
discount
resource
```

Example:

```text
IF action = SEND_QUOTATION
AND amount > 5000 USD
THEN MANAGER_APPROVAL
```

## 6. Approval levels

Possible levels:

- employee;
- supervisor;
- department manager;
- finance;
- director;
- multi-approval.

Do not implement all levels until the underlying policy model is stable.

## 7. Risk classification

Suggested:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

Risk should be metadata used by policy, not an automatic permission decision.

## 8. Autonomy

Autonomy level is a convenience/default setting.

Policy always wins.

```text
Autonomy
   ↓
Policy
   ↓
Authorization
   ↓
Execution
```

## 9. Critical rule

The LLM must never decide:

> "I am allowed to do this."

The backend decides that.
