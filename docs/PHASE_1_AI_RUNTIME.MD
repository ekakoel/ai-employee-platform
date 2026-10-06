# Phase 1 — AI Employee Runtime

**Project:** AI Employee Platform
**Branch:** `development`
**Phase:** 1
**Status:** Planned

---

## 1. Tujuan

Phase 1 bertujuan mengubah `Agent Instance` dari sekadar entity/database record menjadi AI Employee yang dapat:

* menerima task;
* memahami instruksi task;
* membaca context Agent;
* menggunakan LLM;
* memilih tool yang tersedia;
* menjalankan tool melalui Runtime;
* mengikuti permission dan policy perusahaan;
* meminta approval untuk tindakan sensitif;
* menghasilkan hasil pekerjaan;
* mencatat aktivitas ke Audit Log.

Phase ini belum bertujuan membuat AI Employee menjadi sistem SaaS penuh.

Fokus utama adalah membangun **runtime engine yang aman, modular, dan provider-independent**.

---

# 2. Prinsip Arsitektur

AI Employee tidak boleh mempunyai akses langsung ke database atau sistem eksternal.

Semua pekerjaan harus melalui Runtime dan Tool layer.

```text
User
  │
  ▼
Task
  │
  ▼
Agent Runtime
  │
  ├── Agent Context
  ├── Instructions
  ├── LLM Provider
  ├── Tool Selection
  └── Execution Loop
          │
          ▼
     Policy Engine
          │
     ┌────┴────┐
     │         │
    Allow    Approval
     │         │
     │      Human Review
     │         │
     └────┬────┘
          ▼
         Tool
          │
          ▼
   CRM / Database / Service
          │
          ▼
      Audit Log
```

LLM berfungsi sebagai **reasoning/planning component**, bukan sebagai security layer.

Security decision harus tetap ditentukan oleh application runtime.

---

# 3. Scope Phase 1

## 3.1 LLM Provider Abstraction

Membuat interface provider sehingga Agent Runtime tidak bergantung langsung pada Ollama, OpenAI, atau provider tertentu.

Target interface:

```text
LLMProvider
├── chat()
├── generate()
└── tool calling support
```

Provider pertama:

```text
OllamaProvider
```

Model development:

```text
qwen3:1.7b
```

Provider lain dapat ditambahkan kemudian tanpa mengubah Agent Runtime.

---

## 3.2 Agent Context

Runtime harus dapat membangun context berdasarkan:

* Company;
* User;
* Agent Instance;
* Agent Catalog;
* Agent configuration;
* Agent skills;
* Allowed tools;
* Company policies;
* Knowledge;
* Task.

Context harus dibatasi berdasarkan ownership/company isolation.

Agent dari Company A tidak boleh menerima context milik Company B.

---

## 3.3 Agent Instructions

Setiap AI Employee harus mempunyai instruksi dasar.

Contoh:

```text
You are Contract Manager.

Your responsibility is to analyze and manage company contracts.

You must:
- use only available company data;
- use available tools;
- never invent contract information;
- request approval before sensitive actions;
- report uncertainty clearly.
```

Instructions tidak boleh menjadi pengganti permission atau policy enforcement.

---

# 4. Agent Runtime

Membuat komponen:

```text
app/runtime/agent_runtime.py
```

Runtime bertanggung jawab untuk menjalankan lifecycle AI Employee.

Target lifecycle:

```text
Task Created
     │
     ▼
Load Agent
     │
     ▼
Build Context
     │
     ▼
Send Context + Task to LLM
     │
     ▼
LLM Decision
     │
     ├── Final Response
     │
     └── Tool Call
             │
             ▼
        Tool Executor
             │
             ▼
        Policy Engine
             │
       ┌─────┴─────┐
       │           │
     Allow       Approval
       │           │
       ▼           ▼
    Execute      Wait
       │
       ▼
    Tool Result
       │
       ▼
      LLM
       │
       ▼
 Final Response
```

---

# 5. Tool Calling

Agent Runtime harus dapat menerima keputusan LLM berupa tool call.

Contoh:

```json
{
  "tool": "search_contract",
  "arguments": {
    "query": "Villa ABC"
  }
}
```

Runtime kemudian:

1. memvalidasi tool;
2. memvalidasi Agent allowed tools;
3. menjalankan Policy Engine;
4. meminta approval jika diperlukan;
5. menjalankan tool;
6. mengembalikan hasil tool ke LLM;
7. melanjutkan execution loop.

LLM tidak boleh memanggil Python function atau database secara langsung.

---

# 6. Tool Registry

Tool tetap didaftarkan melalui:

```text
app/tools/registry.py
```

Contoh:

```text
Contract Manager
│
├── search_contract
├── get_contract
├── analyze_contract
└── ...
```

Phase 1 hanya perlu memastikan Runtime dapat menggunakan tool yang sudah tersedia.

Tool baru akan ditambahkan pada Phase Contract Manager.

---

# 7. Policy Enforcement

Semua tool call harus melewati:

```text
app/security/policy_engine.py
```

Policy mempunyai tiga kemungkinan:

```text
ALLOW
DENY
REQUIRE_APPROVAL
```

Contoh:

```text
search_contract
    → ALLOW

update_contract
    → REQUIRE_APPROVAL

delete_contract
    → REQUIRE_APPROVAL

unknown_tool
    → DENY
```

LLM tidak boleh menentukan sendiri apakah sebuah tindakan aman.

---

# 8. Approval Workflow

Jika Policy Engine menghasilkan:

```text
REQUIRE_APPROVAL
```

Runtime harus:

1. membuat `Approval`;
2. menyimpan alasan;
3. menyimpan payload/action;
4. mengubah status task menjadi `waiting_approval`;
5. menghentikan execution loop;
6. menunggu keputusan manusia.

Setelah approval diberikan:

```text
Approval
   │
   ▼
Resume Task
   │
   ▼
Execute Tool
   │
   ▼
Continue Runtime
```

---

# 9. Audit

Setiap aktivitas penting harus tercatat.

Minimal:

```text
TASK_STARTED
LLM_REQUEST
TOOL_REQUESTED
TOOL_ALLOWED
TOOL_DENIED
APPROVAL_REQUIRED
TOOL_EXECUTED
TASK_COMPLETED
TASK_FAILED
```

Audit harus mencatat:

* company;
* user;
* agent;
* task;
* action;
* resource;
* status;
* details;
* timestamp.

Audit digunakan untuk monitoring dan debugging AI Employee.

---

# 10. Error Handling

Runtime harus menangani minimal:

```text
LLM unavailable
LLM timeout
Invalid LLM response
Unknown tool
Invalid tool arguments
Tool execution failure
Policy denied
Approval required
Agent inactive
Task not found
Company isolation violation
```

Runtime tidak boleh crash hanya karena LLM menghasilkan response yang tidak valid.

---

# 11. LLM Response Contract

Runtime harus memiliki struktur internal untuk membedakan:

```text
FINAL_RESPONSE
TOOL_CALL
ERROR
```

Contoh:

```json
{
  "type": "tool_call",
  "tool": "search_contract",
  "arguments": {
    "query": "ABC Hotel"
  }
}
```

atau:

```json
{
  "type": "final",
  "content": "I found 3 matching contracts."
}
```

Parsing dan validation dilakukan oleh application layer.

---

# 12. Configuration

LLM configuration harus berasal dari environment/configuration.

Contoh:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
```

Jangan hard-code provider atau model di `AgentRuntime`.

---

# 13. File Structure

Target struktur:

```text
app/
│
├── llm/
│   ├── __init__.py
│   ├── base.py
│   └── ollama.py
│
├── runtime/
│   ├── __init__.py
│   ├── executor.py
│   ├── tool_executor.py
│   └── agent_runtime.py
│
├── agents/
│   ├── __init__.py
│   └── context.py
│
├── security/
│   └── policy_engine.py
│
├── tools/
│   ├── base.py
│   ├── registry.py
│   └── contract.py
│
└── services/
    ├── approval.py
    ├── audit.py
    └── task_runtime.py
```

---

# 14. Implementation Steps

Phase 1 akan dikerjakan secara bertahap.

## Step 1 — LLM Provider Interface

* [ ] Buat `app/llm/`
* [ ] Buat `app/llm/base.py`
* [ ] Definisikan `LLMProvider`
* [ ] Definisikan request/response contract
* [ ] Unit test provider contract

---

## Step 2 — Ollama Provider

* [ ] Buat `app/llm/ollama.py`
* [ ] Connect ke Ollama
* [ ] Load configuration dari environment
* [ ] Implement basic chat
* [ ] Test menggunakan `qwen3:1.7b`

---

## Step 3 — Agent Context

* [ ] Review `app/agents/context.py`
* [ ] Build complete runtime context
* [ ] Include company isolation
* [ ] Include tools
* [ ] Include policies
* [ ] Include knowledge

---

## Step 4 — Agent Runtime

* [ ] Buat `app/runtime/agent_runtime.py`
* [ ] Load Agent Instance
* [ ] Build context
* [ ] Send task ke LLM
* [ ] Parse response
* [ ] Return final response

---

## Step 5 — Tool Calling

* [ ] Detect tool call
* [ ] Validate tool
* [ ] Validate arguments
* [ ] Execute melalui `ToolExecutor`
* [ ] Return tool result ke LLM
* [ ] Continue execution loop

---

## Step 6 — Policy & Approval

* [ ] Integrate Policy Engine
* [ ] Handle `ALLOW`
* [ ] Handle `DENY`
* [ ] Handle `REQUIRE_APPROVAL`
* [ ] Pause task
* [ ] Resume task setelah approval

---

## Step 7 — Audit

* [ ] Record LLM activity
* [ ] Record tool calls
* [ ] Record policy decisions
* [ ] Record approval
* [ ] Record task lifecycle

---

## Step 8 — Integration Tests

Test minimal:

* [ ] Agent dapat menjalankan task
* [ ] Agent inactive ditolak
* [ ] Unknown tool ditolak
* [ ] Unauthorized tool ditolak
* [ ] Policy deny bekerja
* [ ] Approval requirement bekerja
* [ ] Approved tool dapat dieksekusi
* [ ] Tool result kembali ke runtime
* [ ] Task completed
* [ ] Audit tercatat
* [ ] Company isolation tetap bekerja

---

# 15. Contract Manager First Test

Setelah Runtime selesai, AI Employee pertama yang digunakan adalah:

```text
Contract Manager
```

Test pertama:

```text
Company
   │
   ▼
Hire Contract Manager
   │
   ▼
Create Task
   │
   ▼
"Find the contract for Villa ABC"
   │
   ▼
Contract Manager
   │
   ▼
LLM
   │
   ▼
search_contract
   │
   ▼
Company Knowledge
   │
   ▼
Result
   │
   ▼
LLM
   │
   ▼
Final Response
```

AI harus menggunakan data yang tersedia di platform.

AI tidak boleh:

* mengarang contract;
* mengarang harga;
* mengarang supplier;
* mengakses database perusahaan lain;
* menggunakan internet sebagai sumber data;
* menjalankan tool yang tidak diberikan;
* melewati Policy Engine.

---

# 16. CRM Integration Boundary

CRM belum menjadi implementasi utama Phase 1.

Namun Runtime harus dirancang agar nantinya dapat menggunakan:

```text
CRM Tools
    │
    ▼
Tool Executor
    │
    ▼
Policy Engine
    │
    ▼
crm.balikamitour.com
```

AI Employee tidak boleh mendapatkan akses database CRM secara langsung.

Semua akses CRM harus melalui integration/tool layer.

Target Phase berikutnya:

```text
Contract Manager
        │
        ▼
CRM Integration
        │
        ▼
crm.balikamitour.com
```

---

# 17. Security Requirements

Phase 1 wajib mempertahankan:

### Tenant Isolation

Company A tidak dapat membaca data Company B.

### Agent Isolation

Agent hanya dapat menggunakan tools yang diberikan.

### Policy Enforcement

LLM tidak dapat melewati policy.

### Approval Enforcement

Sensitive actions tidak dapat dieksekusi tanpa approval.

### Auditability

Tool calls dan keputusan penting harus dapat ditelusuri.

### No Direct Database Access

LLM tidak boleh menjalankan arbitrary SQL.

### No Arbitrary Code Execution

LLM tidak boleh menjalankan arbitrary Python, PowerShell, shell command, atau executable.

---

# 18. Non-Goals

Phase 1 tidak mencakup:

* billing;
* subscription payment;
* production authentication;
* frontend Control Center;
* vector database;
* OCR;
* document ingestion pipeline lengkap;
* CRM synchronization;
* email automation;
* background worker;
* multi-model optimization;
* autonomous unrestricted execution;
* production deployment.

Fitur tersebut akan dikerjakan pada phase berikutnya.

---

# 19. Definition of Done

Phase 1 dianggap selesai apabila:

* [ ] LLM provider abstraction tersedia.
* [ ] Ollama provider dapat digunakan.
* [ ] `qwen3:1.7b` dapat memberikan response.
* [ ] Agent Runtime dapat menjalankan Task.
* [ ] Agent Context dapat dibangun.
* [ ] Agent dapat melakukan tool call.
* [ ] Tool call melewati Tool Executor.
* [ ] Policy Engine selalu dievaluasi.
* [ ] Approval dapat menghentikan task.
* [ ] Approval dapat melanjutkan task.
* [ ] Audit Log tercatat.
* [ ] Company isolation tetap bekerja.
* [ ] Agent permission tetap bekerja.
* [ ] Error handling bekerja.
* [ ] Integration tests berhasil.
* [ ] Existing Phase 0 tests tetap lulus.

Target akhir:

```text
pytest -q

All tests passed
```

---

# 20. Final Architecture

Setelah Phase 1:

```text
                         AI EMPLOYEE PLATFORM
                                  │
                         ┌────────▼────────┐
                         │  Agent Instance │
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │  Agent Runtime  │
                         └────────┬────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
        Agent Context        LLM Provider        Tool Registry
                                  │                   │
                            ┌─────┴─────┐       ┌─────┴─────┐
                            │           │       │           │
                          Ollama      Future  Contract    CRM
                            │           │       Tools      Tools
                            └─────┬─────┘       └─────┬─────┘
                                  │                   │
                                  └────────┬──────────┘
                                           ▼
                                    Policy Engine
                                           │
                                  ┌────────┴────────┐
                                  │                 │
                                ALLOW          APPROVAL
                                  │                 │
                                  ▼                 ▼
                                Tool           Human Review
                                  │
                                  ▼
                           External Systems
                                  │
                                  ▼
                              Audit Log
```

---

# 21. Phase 1 Success Scenario

The final demonstration should look like this:

```text
User:
"Find the contract for Villa ABC."

        ↓

Contract Manager
        ↓

Agent Runtime
        ↓

LLM
        ↓

search_contract()
        ↓

Policy Engine
        ↓

ALLOW
        ↓

Contract Tool
        ↓

Company Knowledge
        ↓

Contract Result
        ↓

LLM
        ↓

Contract Manager Response
        ↓

Audit Log
```

This proves that the platform has moved from:

```text
AI Employee = Database Record
```

to:

```text
AI Employee = Runtime + Intelligence + Tools + Policy + Approval + Audit
```

which is the foundation required for future AI Employees that can be hired by different companies.
