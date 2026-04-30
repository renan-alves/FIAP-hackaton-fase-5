# Contract Audit — FUN-001: POST /analyze

**Task ID:** T001 — `auditar-contrato-http`  
**Spec Version:** 2.1  
**Date:** 2026-04-30  
**Status:** ✅ Complete  

---

## 1. Executive Summary

Four contract misalignments were found between the current implementation and spec v2.1.
Two are **breaking changes** requiring coordinated flag-day deployment with SOAT (GUD-007).
One is a **missing feature** (metadata field). One is **dead code** that must be cleaned up.

No async/RabbitMQ worker exists — queue flow is not yet implemented, so response structure
changes carry zero risk of async regression.

---

## 2. Files Reviewed

| File | Purpose |
|---|---|
| `ai_module/src/ai_module/api/routes/analyze.py` | Route handler |
| `ai_module/src/ai_module/models/report.py` | Response models |
| `ai_module/src/ai_module/models/request.py` | Request model |
| `ai_module/src/ai_module/core/pipeline.py` | Pipeline + `_build_response()` |
| `ai_module/src/ai_module/main.py` | Exception handlers |
| `ai_module/tests/integration/test_routes.py` | Route integration tests |
| `ai_module/tests/integration/test_analyze_image.py` | Image integration tests |
| `ai_module/tests/integration/test_analyze_pdf.py` | PDF integration tests |
| `ai_module/src/ai_module/worker.py` | Async worker — **does not exist** |

---

## 3. Contract Differences

### 3.1 [BREAKING] Response Structure: Flat → Nested `report`

**Severity:** 🔴 CRITICAL — Primary breaking change  
**Affects:** T002 (input), T003 (response), T004 (tests)

**Current (flat):**

```json
{
  "analysis_id": "...",
  "status": "success",
  "summary": "...",
  "components": [...],
  "risks": [...],
  "recommendations": [...],
  "metadata": {...}
}
```

**Spec v2.1 (nested `report`):**

```json
{
  "analysis_id": "...",
  "status": "success",
  "report": {
    "summary": "...",
    "components": [...],
    "risks": [...],
    "recommendations": [...]
  },
  "metadata": {...}
}
```

**Root Cause:**  
`AnalyzeResponse` in `models/report.py` defines `summary`, `components`, `risks`,
and `recommendations` as direct fields. Spec v2.1 requires these nested inside a
`report: Report` field.

`_build_response()` in `pipeline.py` (line 647) constructs:

```python
return AnalyzeResponse(
    analysis_id=analysis_id,
    status="success",
    summary=report.summary,          # ❌ flat
    components=report.components,    # ❌ flat
    risks=report.risks,              # ❌ flat
    recommendations=report.recommendations,  # ❌ flat
    metadata=ReportMetadata(...),
)
```

**Required change:**

```python
return AnalyzeResponse(
    analysis_id=analysis_id,
    status="success",
    report=report,                   # ✅ nested
    metadata=ReportMetadata(...),
)
```

**Files to modify:**
- `ai_module/src/ai_module/models/report.py` — Remove flat fields from `AnalyzeResponse`, add `report: Report`
- `ai_module/src/ai_module/core/pipeline.py` — Update `_build_response()` to pass `report=report`

---

### 3.2 [BREAKING] Timeout Error Code: `AI_FAILURE` → `AI_TIMEOUT`

**Severity:** 🔴 CRITICAL — Wrong error code in production  
**Affects:** T003 (error handlers), T004 (tests)

**Current `main.py` — `timeout_handler` (line ~175):**

```python
@app.exception_handler(AITimeoutError)
async def timeout_handler(request: Request, exc: AITimeoutError) -> JSONResponse:
    ...
    return JSONResponse(
        status_code=504,
        content=ErrorResponse(
            ...
            error_code="AI_FAILURE",   # ❌ spec requires "AI_TIMEOUT"
            ...
        ).model_dump(),
    )
```

**Spec v2.1 Error Code Table:**

| Error Code | Meaning |
|---|---|
| `AI_FAILURE` | LLM processing failed after allowed retries — status 500 |
| `AI_TIMEOUT` | LLM call exceeded timeout — **status 504** |

**Files to modify:**
- `ai_module/src/ai_module/main.py` — Change `error_code="AI_FAILURE"` to `error_code="AI_TIMEOUT"` in `timeout_handler` only

---

### 3.3 [CLEANUP] Dead UUID Validator in `AnalyzeRequest`

**Severity:** 🟡 IMPORTANT — Contradicts GUD-006, dead code risk  
**Affects:** T002 (input validation)

`models/request.py` defines `AnalyzeRequest` with a `@field_validator("analysis_id")`
that enforces UUID4 format:

```python
@field_validator("analysis_id")
@classmethod
def validate_uuid(cls, v: str) -> str:
    try:
        uuid_obj = uuid.UUID(v, version=4)
        return str(uuid_obj)
    except ValueError:
        raise ValueError("analysis_id must be a valid UUID4 string")
```

**The route does NOT use `AnalyzeRequest` at all.** The route handler in `analyze.py`
uses `Form(...)` directly:

```python
analysis_id: Annotated[str, Form(...)],
```

UUID validation is **NOT active at runtime**. `AnalyzeRequest` is dead code.

**Spec v2.1 GUD-006:** `analysis_id` is a plain string. Validation is delegated to
the orchestrator. This service trusts the provided value.

**Files to modify:**
- `ai_module/src/ai_module/models/request.py` — Remove UUID validator and UUID4 imports

---

### 3.4 [MISSING] `downsampling_applied` Field in `ReportMetadata`

**Severity:** 🟡 IMPORTANT — Field present in spec response example and AC-012  
**Affects:** T003 (response models)

**Spec v2.1 metadata example:**

```json
"metadata": {
  "model_used": "string",
  "processing_time_ms": 1200,
  "input_type": "image",
  "context_text_provided": true,
  "context_text_length": 128,
  "downsampling_applied": false,    // ← present in spec
  "conflict_detected": false,
  "conflict_decision": "NO_CONFLICT",
  "conflict_policy": "DIAGRAM_FIRST"
}
```

**AC-012:** "Given an input image larger than the configured processing threshold, when
preprocessing occurs, then the service SHALL downsample the image and mark
`downsampling_applied` as `true`."

**Current `ReportMetadata` model:** field does not exist.
`StrictModel` uses `extra="forbid"` — the field will never appear in responses.

**Files to modify:**
- `ai_module/src/ai_module/models/report.py` — Add `downsampling_applied: bool = False` to `ReportMetadata`
- `ai_module/src/ai_module/core/pipeline.py` — Pass `downsampling_applied=<bool>` when building metadata

---

## 4. Async Flow Impact Assessment

| Item | Finding |
|---|---|
| `ai_module/src/ai_module/worker.py` | **Does not exist** |
| `QueueJobMessage` | **Not implemented** |
| `QueueResultMessage` | **Not implemented** |
| RabbitMQ queue models | **Not implemented** |

**Conclusion:** The async/RabbitMQ flow from spec section 4.2 is not yet implemented.
Response structure changes (item 3.1) carry **zero risk of async regression** because
there is no worker to break.

AC-006 and AC-007 (queue consumer behavior) are out of scope for this feature.

---

## 5. Test Impact Map

### Tests that directly access flat response fields (will fail after T003)

| File | Line | Assertion | Action Required |
|---|---|---|---|
| `test_analyze_image.py` | ~35 | `body["summary"]` | → `body["report"]["summary"]` |
| `test_analyze_image.py` | ~55 | `body["components"]` | → `body["report"]["components"]` |
| `test_analyze_image.py` | ~72 | `body["risks"]` | → `body["report"]["risks"]` |
| `test_analyze_image.py` | ~89 | `body["recommendations"]` | → `body["report"]["recommendations"]` |
| `test_analyze_pdf.py` | ~28 | `body["summary"]` | → `body["report"]["summary"]` |
| `test_analyze_pdf.py` | ~48 | `body["components"]` | → `body["report"]["components"]` |
| `test_analyze_pdf.py` | ~62 | `body["risks"]` | → `body["report"]["risks"]` |
| `test_analyze_pdf.py` | ~76 | `body["recommendations"]` | → `body["report"]["recommendations"]` |

### Tests that are already correct (no changes needed)

| File | Notes |
|---|---|
| `test_routes.py` | Accesses only `status`, `analysis_id`, `metadata.input_type` — OK |
| `test_analyze_image.py` | `metadata` field access is OK |
| `test_analyze_pdf.py` | `metadata` field access is OK |

### Missing test coverage

| Gap | Required Action |
|---|---|
| Timeout → `error_code="AI_TIMEOUT"` | Add test asserting 504 + `AI_TIMEOUT` |
| `analysis_id` with non-UUID format accepted | Add test per GUD-006 |

---

## 6. Contract Validation Checklist

### For T002 (Input Validation)
- [ ] `analysis_id` accepted as plain string (remove dead UUID validator from `request.py`)
- [ ] `context_text` max 1000 chars → 422 `INVALID_INPUT` (already implemented via `Form(max_length=...)`)
- [ ] No UUID validation at runtime (already absent in route — confirm remains absent)

### For T003 (Response Structure & Error Codes)
- [ ] `AnalyzeResponse.report` field of type `Report` replaces flat fields
- [ ] `_build_response()` passes `report=report` (not flat fields)
- [ ] `timeout_handler` uses `error_code="AI_TIMEOUT"` (not `AI_FAILURE`)
- [ ] `ReportMetadata` includes `downsampling_applied: bool = False`
- [ ] Pipeline passes `downsampling_applied` flag to `ReportMetadata`

### For T004 (Tests)
- [ ] All `body["summary"]` → `body["report"]["summary"]`
- [ ] All `body["components"]` → `body["report"]["components"]`
- [ ] All `body["risks"]` → `body["report"]["risks"]`
- [ ] All `body["recommendations"]` → `body["report"]["recommendations"]`
- [ ] Add test: timeout → 504 + `error_code="AI_TIMEOUT"`
- [ ] Add test: non-UUID `analysis_id` → 200 (accepted per GUD-006)

### For T005 (Documentation & Quality Gates)
- [ ] `ruff check` passes
- [ ] `ruff format --check` passes
- [ ] `mypy --strict` passes
- [ ] `pytest --cov` ≥ 80% coverage
- [ ] `docs/MIGRATION-FUN-001.md` created
- [ ] Contract test skeleton in `tests/contract/`

---

## 7. Files Requiring Modification

| File | Change Type | Description |
|---|---|---|
| `ai_module/src/ai_module/models/report.py` | Modify | Remove flat fields from `AnalyzeResponse`, add `report: Report`; add `downsampling_applied` to `ReportMetadata` |
| `ai_module/src/ai_module/core/pipeline.py` | Modify | Update `_build_response()` to use `report=report`; pass `downsampling_applied` |
| `ai_module/src/ai_module/main.py` | Modify | Change `error_code="AI_FAILURE"` → `"AI_TIMEOUT"` in `timeout_handler` |
| `ai_module/src/ai_module/models/request.py` | Modify | Remove UUID4 validator (dead code cleanup per GUD-006) |
| `ai_module/tests/integration/test_analyze_image.py` | Modify | Update flat field assertions to nested `report` access |
| `ai_module/tests/integration/test_analyze_pdf.py` | Modify | Update flat field assertions to nested `report` access |
| `ai_module/tests/integration/test_routes.py` | Modify | Add timeout `AI_TIMEOUT` test; add non-UUID `analysis_id` test |
| `docs/MIGRATION-FUN-001.md` | Create | Migration guide for SOAT team (T005) |
| `ai_module/tests/contract/__init__.py` | Create | Contract test package (T005) |
| `ai_module/tests/contract/test_soat_contract.py` | Create | Contract test skeleton (T005) |

---

## 8. Breaking Changes Summary (for Migration Guide)

| # | What Changed | Before | After |
|---|---|---|---|
| 1 | Response body structure | Flat: `body.summary`, `body.components`, etc. | Nested: `body.report.summary`, `body.report.components`, etc. |
| 2 | Timeout error code | `"error_code": "AI_FAILURE"` on 504 | `"error_code": "AI_TIMEOUT"` on 504 |

**Non-breaking additions:**
- `metadata.downsampling_applied` field (new, defaults to `false`)

---

## 9. Recommended Execution Order for Tasks T002–T003

T002 and T003 operate on different files and can run in parallel:

| Task | Files |
|---|---|
| T002 | `models/request.py` only |
| T003 | `models/report.py`, `core/pipeline.py`, `main.py` |
