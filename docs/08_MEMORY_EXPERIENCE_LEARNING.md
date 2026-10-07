# Memory, Experience and Controlled Learning

## 1. Three distinct concepts

### Knowledge

Company-provided facts and documents.

### Memory

Useful contextual information retained for future interactions.

### Experience

A structured record of a previous problem, decision, result and lesson.

## 2. Experience lifecycle

```text
Task
 ↓
Decision
 ↓
Action
 ↓
Result
 ↓
Human feedback
 ↓
Experience candidate
 ↓
Validation
 ↓
Reusable experience
```

## 3. Experience record

Conceptual fields:

```text
situation
context
problem
decision
action
result
human_correction
lesson
confidence
validation_status
source_task
created_at
```

## 4. Retrieval

For a new task:

```text
New Task
 ↓
Find similar validated experiences
 ↓
Rank relevance
 ↓
Inject useful experience into context
 ↓
AI decision
```

## 5. Confidence

Experience should have confidence based on:

- similarity;
- outcome quality;
- number of successful repetitions;
- human validation;
- freshness.

Low-confidence experience should be advisory, not authoritative.

## 6. Learning boundaries

AI must not automatically:

- change company policy;
- grant itself permission;
- change approval requirements;
- modify its own security boundary;
- alter financial rules;
- permanently change critical behavior without governance.

## 7. Continuous improvement

A useful improvement loop:

```text
AI Output
 ↓
Human Correction
 ↓
Evaluation
 ↓
Training Example / Experience
 ↓
Validation
 ↓
Future Retrieval
```

This gives the Agent a practical way to improve without requiring immediate per-company model fine-tuning.
