# AI Employee Platform — Session Handoff Report

**Project:** `ai-employee-platform`
**Path:** `D:\Eka Koel\App\2026\AI\ai-employee-platform`
**Date:** 2026-10-06
**Session Focus:** Step 5AL — LLM Runtime Integration & Dependency Injection

---

## 1. Project Objective

Project ini dikembangkan sebagai **AI Employee Platform / SaaS**.

Konsep utama:

```text
Company
   ↓
Hire AI Employee
   ↓
AI Agent
   ↓
Agent Runtime
   ↓
LLM
   ↓
Tool
   ↓
Policy / Permission
   ↓
Human Approval (jika diperlukan)
   ↓
Execution
```

Target jangka panjang:

* perusahaan dapat merekrut AI Employee;
* setiap AI Employee memiliki role, skill, knowledge, tools, dan policy;
* AI dapat menjalankan pekerjaan melalui tools;
* tindakan sensitif wajib melalui human approval;
* platform nantinya dapat digunakan oleh banyak perusahaan;
* architecture harus multi-company / tenant-aware;
* LLM provider harus dapat diganti tanpa mengubah business logic.

---

# 2. Security Architecture

Architecture yang sedang dipertahankan:

```text
LLM
 ↓
AgentRuntime
 ↓
ToolExecutor
 ↓
Policy / Permission / Approval
 ↓
Tool
```

Untuk action yang membutuhkan approval:

```text
Tool Call
   ↓
ToolExecutor
   ↓
Policy Engine
   ↓
require_approval
   ↓
Approval Record
   ↓
PENDING
   ↓
Human Review
 /        \
APPROVE   REJECT
  ↓         ↓
Execute   Stop Action
```

Task lifecycle:

```text
Task
 ↓
Tool requires approval
 ↓
Approval PENDING
 ↓
Task WAITING_APPROVAL
 ↓
APPROVE
 ↓
Task RESUME
 ↓
Tool EXECUTE
 ↓
Task SUCCESS
```

Reject:

```text
REJECT
 ↓
Approval REJECTED
 ↓
Task STOPPED / FAILED
 ↓
Tool never executes
```

**Security principle:**

`AgentRuntime` tidak boleh bypass `ToolExecutor`.

---

# 3. Work Completed Before This Session

Steps berikut sudah selesai dan telah diaudit:

* 5A Tool Decision
* 5B Decision Parser
* 5C Tool Execution Adapter
* 5D Tool Result Feedback Loop
* 5E Native Ollama Tool Payload
* 5F Tool Schema from Registry
* 5G ToolRegistry → Runtime
* 5H Tool Authorization Boundary
* 5I Real Ollama Tool Calling
* 5J Tool Execution Loop
* 5K Approval Flow
* 5L Concurrency Audit & Fix
* 5M Approval Lifecycle Hardening
* 5N Centralized Task Rejection Lifecycle
* 5O Lifecycle Audit / Direct Route Mutation Removal
* 5P Concurrent Resume Hardening
* 5Q Audit `ToolExecutor.execute_approved()`
* 5R Audit Direct Tool Endpoint / Permission
* 5S Audit `AgentRuntime`
* 5T Audit LLM Providers / Construction
* 5U Approval Propagation Regression Test
* 5V AgentExecutor Constructor Audit
* 5W TaskRuntimeService Constructor Audit
* 5X Full `app/runtime/executor.py` Audit
* 5Y AgentExecutor Test Audit
* 5Z AgentExecutor Test Suite
* 5AA TaskRuntimeService ↔ AgentExecutor Audit
* 5AB Approval API Lifecycle Audit
* 5AC Production Construction Path Audit
* 5AD AgentRuntime / AgentContext Audit
* 5AE Config / Main Audit
* 5AF Task / Approval Route Audit
* 5AG AgentExecutor Constructor Audit
* 5AH ToolRegistry Audit
* 5AI Tool Registration Audit
* 5AJ ToolExecutor Constructor Audit
* 5AK Test Construction Audit

---

# 4. Step 5AL — LLM Integration

## 5AL.1 — AgentExecutor LLM Execution

`app/runtime/executor.py` sekarang memiliki:

```python
execute_with_llm(
    db,
    context,
    provider,
    temperature=0.0,
    max_tool_iterations=5,
)
```

Method tersebut membuat:

```text
ToolExecutor
   ↓
ToolRegistry
   ↓
AgentRuntime
   ↓
LLMProvider
```

Important:

`execute()` deterministic tetap dipertahankan.

`execute_approved()` tetap tidak memanggil LLM.

Approved action langsung menggunakan stored approval payload.

Test result:

```text
7 passed
```

---

# 5. TaskRuntimeService Dependency Injection

File:

```text
app/services/task_runtime.py
```

Constructor sekarang:

```python
def __init__(
    self,
    executor: AgentExecutor | None = None,
    provider: LLMProvider | None = None,
):
    self.executor = executor or AgentExecutor()
    self.provider = provider or create_llm_provider()
```

Dengan architecture:

```text
TaskRuntimeService()
        ↓
create_llm_provider()
        ↓
configured provider
```

Tetapi test masih dapat inject fake provider:

```python
TaskRuntimeService(
    executor=executor,
    provider=provider,
)
```

---

# 6. LLM Provider Factory

File baru:

```text
app/runtime/factory.py
```

Current implementation:

```python
from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider


def create_llm_provider() -> LLMProvider:
    """
    Create the configured LLM provider for the application.

    Provider selection is controlled by Settings so API routes
    and runtime services do not depend directly on a specific
    LLM implementation.
    """

    provider_name = settings.llm_provider.strip().lower()

    if provider_name == "ollama":
        return OllamaProvider(settings)

    raise ValueError(
        f"Unsupported LLM provider: '{settings.llm_provider}'."
    )
```

Factory verification sudah berhasil:

```text
OllamaProvider
qwen3:1.7b
```

Current configuration:

```text
llm_provider = ollama
ollama_base_url = http://127.0.0.1:11434
ollama_model = qwen3:1.7b
```

---

# 7. TaskRuntimeService LLM Method

`app/services/task_runtime.py` sekarang memiliki method:

```python
execute_with_llm(
    db,
    company_id,
    task_id,
    temperature=0.0,
    max_tool_iterations=5,
)
```

Flow:

```text
TaskRuntimeService
       ↓
load Task
       ↓
load AgentInstance
       ↓
load AgentContext
       ↓
AgentExecutor.execute_with_llm()
       ↓
AgentRuntime
       ↓
LLMProvider
```

Method ini sengaja dibuat terpisah dari existing:

```python
execute()
```

Tujuannya menjaga backward compatibility selama LLM integration belum selesai.

---

# 8. AgentContext Security Boundary

`AgentContext` sudah diaudit dan tidak perlu diubah.

Source:

```text
app/agents/context.py
```

Context menggunakan:

```text
Company
AgentInstance
Task
Knowledge
Configuration
```

`load_agent_context()` memastikan:

* Agent memiliki company;
* Task berada pada company yang sama;
* Task menggunakan AgentInstance yang sama;
* knowledge hanya berasal dari company;
* knowledge aktif;
* knowledge global atau knowledge khusus agent dapat digunakan sesuai filter.

Ini adalah boundary penting sebelum data dikirim ke LLM.

---

# 9. AgentRuntime

File:

```text
app/runtime/agent_runtime.py
```

Responsibilities:

```text
build system message
build task message
        ↓
get allowed LLM tools
        ↓
LLM provider.chat()
        ↓
Decision Parser
        ↓
Tool decision
        ↓
ToolExecutor
        ↓
tool result
        ↓
LLM kembali reasoning
```

Bounded tool loop:

```python
max_tool_iterations=5
```

LLM hanya melihat tools yang tersedia melalui:

```python
tool_registry.llm_tools(
    context.allowed_tools
)
```

Tool execution tetap melalui:

```python
ToolExecutor.execute()
```

---

# 10. ToolRegistry

File:

```text
app/tools/registry.py
```

Registry saat ini menyediakan:

```python
register()
get()
all()
llm_tools()
```

`llm_tools()` melakukan filtering berdasarkan:

```python
context.allowed_tools
```

Kemudian mengubah `AgentTool` menjadi:

```python
LLMTool
```

Jadi LLM tidak otomatis mendapatkan semua tool.

---

# 11. ToolExecutor

File:

```text
app/runtime/tool_executor.py
```

ToolExecutor adalah security boundary utama.

Saat ini constructor membuat:

```text
ToolRegistry
SearchContractTool
PolicyEngine
ApprovalService
```

Flow execution:

```text
Tool Call
 ↓
ToolExecutor
 ↓
validate company
 ↓
validate agent
 ↓
validate tool
 ↓
PolicyEngine
 ↓
allow / deny / require approval
 ↓
execute
```

`execute_approved()` menggunakan approval record sebagai source of truth.

Ia **tidak menerima arbitrary arguments dari caller**.

Approved execution tetap melakukan security revalidation:

* company;
* task;
* approval status;
* agent;
* agent company;
* agent active;
* allowed tool;
* tool existence;
* current policy.

---

# 12. Critical Exception Mapping Completed

Sebelum Step 5AL.8 terdapat mismatch:

```text
ToolExecutor
    ↓
ApprovalRequiredError
```

sedangkan TaskRuntimeService mengenali:

```text
RuntimeApprovalRequiredError
```

`AgentExecutor.execute_with_llm()` sekarang melakukan mapping:

```python
except ApprovalRequiredError as exc:
    raise RuntimeApprovalRequiredError(
        str(exc),
        approval_id=exc.approval_id,
    ) from exc
```

Dengan demikian:

```text
LLM
 ↓
AgentRuntime
 ↓
ToolExecutor
 ↓
ApprovalRequiredError
 ↓
AgentExecutor
 ↓
RuntimeApprovalRequiredError
 ↓
TaskRuntimeService
```

Ini adalah prerequisite penting sebelum production LLM task lifecycle diaktifkan.

---

# 13. Tests Created / Updated

File:

```text
tests/test_agent_executor.py
```

Saat ini:

```text
7 passed
```

File:

```text
tests/test_task_runtime_llm.py
```

Test yang dibuat:

### Provider injection

Memastikan:

```python
TaskRuntimeService(provider=provider)
```

menggunakan provider tersebut.

### Executor delegation

Memastikan:

```text
TaskRuntimeService
 ↓
AgentExecutor.execute_with_llm()
```

dan context/provider diteruskan dengan benar.

Current result setelah perbaikan test:

```text
2 passed
```

---

# 14. Latest Regression Test

Command terakhir yang berhasil:

```powershell
pytest -q tests\test_task_runtime_llm.py tests\test_agent_executor.py tests\test_approval_lifecycle.py
```

Result:

```text
17 passed, 1 warning in 20.47s
```

Warning:

```text
StarletteDeprecationWarning:
Using httpx with starlette.testclient is deprecated;
install httpx2 instead.
```

Warning ini bukan failure dan belum ditangani karena bukan bagian dari LLM integration.

---

# 15. Current Status

## Completed

```text
5AL.1  AgentExecutor LLM path          ✅
5AL.3  TaskRuntimeService provider DI  ✅
5AL.4  Provider factory                ✅
5AL.5  TaskRuntime LLM method          ✅
5AL.6  TaskRuntime LLM tests           ✅
5AL.7  Provider auto factory           ✅
5AL.8  Approval exception mapping      ✅
```

Latest regression:

```text
17 passed
```

---

# 16. Current Unfinished Work

**Step 5AL.9 sedang berjalan.**

Tujuan:

Memastikan:

```text
LLM
 ↓
Tool call
 ↓
ToolExecutor
 ↓
ApprovalRequiredError
 ↓
RuntimeApprovalRequiredError
 ↓
TaskRuntimeService
 ↓
WAITING_APPROVAL
```

Test yang sedang dibuat:

```text
tests/test_task_runtime_llm.py
```

Test name:

```python
test_llm_approval_required_is_propagated_as_runtime_approval
```

Test ini belum dikonfirmasi hasil akhirnya dalam session handoff ini.

---

# 17. VERY IMPORTANT — Do Not Do Yet

Jangan langsung mengubah endpoint:

```text
POST /companies/{company_id}/tasks/{task_id}/execute
```

menjadi LLM execution.

Alasannya:

Existing endpoint masih menggunakan:

```python
runtime = TaskRuntimeService()

runtime.execute(...)
```

dan deterministic execution masih merupakan jalur production yang aman.

LLM production wiring baru dilakukan setelah:

1. exception propagation test selesai;
2. approval → WAITING_APPROVAL test selesai;
3. LLM success → COMPLETED test selesai;
4. LLM tool execution test selesai;
5. approval resume menggunakan LLM lifecycle diverifikasi;
6. full regression test berhasil.

---

# 18. Critical Architectural Rule

Jangan memindahkan policy atau approval logic ke LLM.

LLM hanya menentukan:

```text
"Tool apa yang ingin saya gunakan?"
```

LLM **tidak menentukan**:

```text
"Apakah saya boleh menggunakan tool tersebut?"
```

Permission tetap:

```text
AgentContext
 ↓
ToolRegistry filtering
 ↓
ToolExecutor
 ↓
PolicyEngine
 ↓
ApprovalService
```

---

# 19. Current Production Construction

Saat ini production route masih:

```python
runtime = TaskRuntimeService()
```

Constructor sekarang otomatis memiliki:

```text
TaskRuntimeService()
       ↓
create_llm_provider()
       ↓
OllamaProvider
       ↓
qwen3:1.7b
```

Namun existing task endpoint belum memanggil:

```python
execute_with_llm()
```

Ini **disengaja**.

---

# 20. Next Step — Exact Continuation

Chat berikutnya harus dilanjutkan dari:

## Step 5AL.9

Pertama, jalankan:

```powershell
pytest -q tests\test_task_runtime_llm.py
```

Jika:

```text
3 passed
```

maka lanjutkan ke:

## Step 5AL.10

Test real task lifecycle:

```text
Task
 ↓
TaskRuntimeService.execute_with_llm()
 ↓
AgentExecutor
 ↓
AgentRuntime
 ↓
LLM
 ↓
Tool requires approval
 ↓
Approval created
 ↓
Task WAITING_APPROVAL
```

Setelah itu baru:

```text
5AL.11
Approval APPROVED
 ↓
resume_after_approval()
 ↓
execute approved tool
 ↓
Task COMPLETED
```

Kemudian:

```text
5AL.12
Approval REJECTED
 ↓
reject_after_approval()
 ↓
Task FAILED
```

Kemudian:

```text
5AL.13
Full regression
```

Baru setelah semua stabil:

```text
5AL.14
Production endpoint LLM wiring
```

---

# 21. Development Rules for Next Session

Ikuti aturan ini tanpa perlu ditanyakan ulang:

1. Jangan meminta source file yang sudah diberikan/audited.
2. Jangan meminta user mengulang hasil test yang sudah diketahui.
3. Jangan melakukan speculative changes.
4. Inspect existing architecture sebelum mengubah production code.
5. Jangan merusak deterministic execution.
6. Jangan bypass `ToolExecutor`.
7. Jangan bypass `PolicyEngine`.
8. Jangan bypass `ApprovalService`.
9. Jangan memanggil LLM kembali untuk `execute_approved()`.
10. Jangan mengubah database secara destructive.
11. Jangan commit Git dulu.
12. Untuk perubahan file, berikan **full-file code** jika memang perlu mengganti file.
13. Gunakan test terlebih dahulu sebelum production wiring.
14. Jalankan command **satu per satu**.
15. Jangan meminta upload/paste output kecuali command benar-benar gagal atau output tersebut memang diperlukan untuk diagnosis.
16. Pertahankan multi-company isolation.
17. Approval harus tetap menjadi human security boundary.
18. LLM provider harus tetap configurable melalui factory.
19. Ollama saat ini adalah provider development:

    ```text
    qwen3:1.7b
    ```
20. Jangan mengganti model/provider tanpa alasan teknis dan test.

---

# 22. One-Line Session State

```text
AI Employee Platform sudah memiliki LLM runtime + provider factory + TaskRuntimeService LLM path + approval exception mapping; deterministic lifecycle tetap aman; latest regression 17 passed; next exact step adalah menyelesaikan Step 5AL.9 untuk membuktikan LLM approval-required → RuntimeApprovalRequiredError sebelum production endpoint diaktifkan.
```

---

# 23. Project Philosophy

Target akhir architecture:

```text
                    ┌──────────────────┐
                    │      Company     │
                    └────────┬─────────┘
                             │
                       Hire AI Employee
                             │
                    ┌────────▼─────────┐
                    │   AgentInstance  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   AgentContext   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   AgentRuntime   │
                    └────────┬─────────┘
                             │
                         LLM Provider
                             │
                    ┌────────▼─────────┐
                    │   Tool Decision  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   ToolExecutor   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   PolicyEngine   │
                    └───────┬─┬────────┘
                            │ │
                       ALLOW│ │REQUIRE
                            │ │
                            │ ▼
                            │ ApprovalService
                            │       │
                            │   Human Review
                            │       │
                            │   APPROVE / REJECT
                            │
                    ┌───────▼──────────┐
                    │       Tool       │
                    └──────────────────┘
```

**Status keseluruhan: Architecture security boundary sudah terbentuk. Sekarang fokusnya adalah menyelesaikan integrasi LLM dengan task lifecycle secara aman sebelum endpoint production diaktifkan.**
