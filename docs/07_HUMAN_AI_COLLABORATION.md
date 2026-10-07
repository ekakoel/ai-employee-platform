# Human + AI + AI Collaboration Model

## 1. Human-to-AI

A human may:

- assign a task;
- ask a question;
- request a recommendation;
- request a draft;
- request execution;
- review output;
- approve/reject.

## 2. AI-to-human

An AI may:

- return results;
- ask clarifying questions;
- request approval;
- escalate;
- recommend an action;
- report failure.

## 3. AI-to-AI

AI Agents communicate through structured tasks.

Example:

```text
Reservation AI
  |
  | CHECK_PAYMENT
  v
Accounting AI
  |
  | PAYMENT_CONFIRMED
  v
Reservation AI
```

## 4. Outside-scope delegation

```text
Human
  ↓
Reservation AI
  ↓
Scope check
  ↓
Accounting capability detected
  ↓
Accounting AI
  ↓
Result
  ↓
Reservation AI
  ↓
Human
```

## 5. Consultation

Consultation does not necessarily create an external action.

Example:

```text
Human:
"Should we give this customer a 10% discount?"

Reservation AI:
- recommendation;
- rationale;
- expected impact;
- alternatives;
- confidence;
- relevant past experience.
```

## 6. Escalation

Escalate when:

- confidence is low;
- policy requires human judgment;
- required capability is unavailable;
- required information is missing;
- task is outside permitted authority.

## 7. Human control

A human can:

- stop/cancel a task where supported;
- reject an approval;
- override a recommendation through authorized business processes;
- provide feedback;
- change policy if authorized.

AI should not silently override human decisions.

## 8. AI workforce

One human may manage multiple AI Agents.

One AI Agent may serve multiple authorized humans.

This relationship should be modeled as assignments/access, not permanent ownership.
