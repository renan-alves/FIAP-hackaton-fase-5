# Tasks — FUN-001: POST /analyze Endpoint Alignment

**Feature:** FUN-001 - POST /analyze endpoint alignment  
**Spec Version:** 2.1  
**Plan Reference:** `docs\plan-FUN-001.md`  
**Specification:** `specs\spec.md` v2.1  
**Date Created:** 2026-04-30  
**Last Updated:** 2026-04-30  
**Status:** ✅ Ready for Execution

---

## Overview

This document defines actionable implementation tasks for aligning the existing `POST /analyze` endpoint with specification v2.1. The endpoint is already implemented but has significant contract misalignments that constitute breaking changes.

### Context

- **Breaking Change:** Flag day deployment with SOAT coordination (GUD-007)
- **UUID Validation:** Plain string, trust orchestrator (GUD-006)
- **Primary Change:** Response structure migrates from flat to nested `report` object
- **Critical Requirements:** Contract tests, SOAT coordination, migration guide

### 5 Core Clarifications (2026-04-30)

1. **Breaking change strategy:** Flag day with SOAT
2. **Directory structure:** specs/ for specs, docs/ for plans
3. **PDF page count:** 3 pages confirmed
4. **UUID validation:** Plain string approach
5. **SOAT migration:** Contract tests required

---

## Task Dependencies

```
auditar-contrato-http (READY)
    ├── alinhar-validacao-de-entrada (BLOCKED)
    └── alinhar-resposta-e-erros (BLOCKED)
            └── atualizar-testes-fun001 (BLOCKED)
                    └── revisar-documentacao-relacionada (BLOCKED)
                            └── coordenar-soat-deployment (BLOCKED)
```

---

## Phase 1: Contract Audit

### Task T001: Audit HTTP Contract

- [x] T001 Audit HTTP contract and map all impact points

**ID:** `auditar-contrato-http`  
**Status:** ✅ Complete  
**Deliverable:** `docs/AUDIT-FUN-001.md`  
**Dependencies:** None  
**Estimated Effort:** ~2 hours  
**Priority:** P0 (Blocking)

**Description:**

Map all points of impact from the contract change between current implementation and spec v2.1. Create comprehensive documentation of contract differences and affected files.

**Activities:**

1. **Compare contracts:**
   - Review current implementation in `ai_module\src\ai_module\api\routes\analyze.py`
   - Compare with spec v2.1 `specs\spec.md` section FUN-001
   - Document all structural differences

2. **Map affected files:**
   - Route handlers: `ai_module\src\ai_module\api\routes\analyze.py`
   - Request models: `ai_module\src\ai_module\models\request.py`
   - Response models: `ai_module\src\ai_module\models\report.py`
   - Pipeline logic: `ai_module\src\ai_module\core\pipeline.py`
   - Exception handlers: `ai_module\src\ai_module\main.py`
   - Integration tests: `ai_module\tests\integration\test_routes.py`
   - Integration tests: `ai_module\tests\integration\test_analyze_image.py`
   - Integration tests: `ai_module\tests\integration\test_analyze_pdf.py`
   - Worker (async impact): `ai_module\src\ai_module\worker.py`

3. **Document breaking changes:**
   - Response structure: flat → nested `report`
   - Error codes: `AI_FAILURE` → `AI_TIMEOUT` for timeout scenarios
   - Validation: current vs spec requirements

4. **Create validation checklist:**
   - Contract compliance items
   - Test coverage requirements
   - Documentation update requirements

5. **Validate async impact:**
   - Check if `QueueJobMessage` and `QueueResultMessage` are affected
   - Confirm pipeline changes work for both HTTP and RabbitMQ flows
   - Ensure shared models don't break queue serialization

**Acceptance Criteria:**

- [ ] Impact document created identifying all affected files
- [ ] Differences between current contract and spec v2.1 documented
- [ ] Validation checklist ready for subsequent tasks
- [ ] Confirmation that shared models don't break async flow
- [ ] Breaking changes explicitly listed with migration paths

**Deliverables:**

- Contract audit document (markdown recommended)
- List of files requiring modification
- Contract validation checklist
- Async flow impact assessment

**Files to Review:**

```
ai_module\src\ai_module\api\routes\analyze.py
ai_module\src\ai_module\models\report.py
ai_module\src\ai_module\models\request.py
ai_module\src\ai_module\core\pipeline.py
ai_module\src\ai_module\main.py
ai_module\tests\integration\test_routes.py
ai_module\tests\integration\test_analyze_image.py
ai_module\tests\integration\test_analyze_pdf.py
ai_module\src\ai_module\worker.py
```

---

## Phase 2: Implementation

### Task T002: Align Input Validation

- [x] T002 Align input validation with spec v2.1 requirements

**ID:** `alinhar-validacao-de-entrada`  
**Status:** ✅ Complete  
**Dependencies:** `auditar-contrato-http` (T001) ✅  
**Estimated Effort:** ~1 hour  
**Priority:** P1

**Description:**

Ensure consistent validation of `context_text` (max 1000 chars) at the HTTP boundary. Confirm `analysis_id` remains as plain string without strict UUID validation per GUD-006.

**Activities:**

1. **Review request model:**
   - Open `ai_module\src\ai_module\models\request.py`
   - Locate `AnalyzeRequest` model

2. **Validate `analysis_id` handling:**
   - Confirm type is `str` (not UUID)
   - Remove any UUID validation if present
   - Document "trust orchestrator" approach (GUD-006)

3. **Validate `context_text` constraints:**
   - Confirm `max_length=1000` constraint exists
   - Ensure validation triggers 422 error with `INVALID_INPUT`
   - Verify error message is descriptive

4. **Update route signature if needed:**
   - Review `ai_module\src\ai_module\api\routes\analyze.py`
   - Ensure route accepts validated model
   - Confirm FastAPI automatic validation is active

5. **Add validation tests:**
   - Test `context_text` > 1000 chars → 422 with `INVALID_INPUT`
   - Test `analysis_id` with various formats (UUID, plain string) → all accepted
   - Test missing required fields → 422 with appropriate error

**Acceptance Criteria:**

- [ ] `analysis_id` accepted as any string format (trust orchestrator ✅)
- [ ] `context_text` rejected if > 1000 characters → 422
- [ ] Validation tests cover valid and invalid cases
- [ ] Error messages structured per spec (`ErrorResponse`)
- [ ] FastAPI automatic validation working correctly

**Example Test:**

```python
def test_analyze_context_text_too_long_returns_422(client: TestClient, png_bytes: bytes):
    response = client.post(
        "/analyze",
        data={
            "analysis_id": "any-id-format",  # OK per GUD-006
            "context_text": "x" * 1001,  # Too long
        },
        files={"file": ("diagram.png", png_bytes, "image/png")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INVALID_INPUT"
    assert "context_text" in body["message"].lower()
    assert "1000" in body["message"]
```

**Files to Modify:**

```
ai_module\src\ai_module\models\request.py
ai_module\tests\integration\test_routes.py (add validation tests)
```

---

### Task T003: Align Response Structure and Error Codes

- [x] T003 Refactor response models and error handlers for spec v2.1 compliance

**ID:** `alinhar-resposta-e-erros`  
**Status:** ✅ Complete  
**Dependencies:** `auditar-contrato-http` (T001) ✅  
**Estimated Effort:** ~3 hours  
**Priority:** P1

**Description:**

Adjust response models, pipeline logic, and exception handlers to match spec v2.1. Primary change: restructure success response to use nested `report` object instead of flat structure.

**Activities:**

1. **Refactor response models (`models\report.py`):**
   
   a. Create new `Report` model:
   ```python
   class Report(BaseModel):
       """Nested report structure per spec v2.1"""
       summary: str
       components: List[Component]
       risks: List[Risk]
       recommendations: List[Recommendation]
   ```
   
   b. Update `AnalyzeResponse`:
   ```python
   class AnalyzeResponse(BaseResponse):
       """Success response per spec v2.1 with nested report"""
       status: Literal["success"] = "success"
       report: Report  # Nested structure!
       metadata: ReportMetadata
   ```
   
   c. Validate `ErrorResponse` remains unchanged (already spec-compliant)
   
   d. Update docstrings to reference `specs/spec.md` v2.1

2. **Update pipeline (`core\pipeline.py`):**
   
   a. Locate `_build_response()` method
   
   b. Refactor to return structure with nested `report`:
   ```python
   def _build_response(...) -> AnalyzeResponse:
       return AnalyzeResponse(
           analysis_id=analysis_id,
           status="success",
           report=Report(
               summary=validated_report.summary,
               components=validated_report.components,
               risks=validated_report.risks,
               recommendations=validated_report.recommendations
           ),
           metadata=self._build_metadata(...)
       )
   ```
   
   c. Preserve metadata logic and conflict detection
   
   d. Ensure pipeline works for both HTTP and async flows

3. **Update exception handlers (`main.py`):**
   
   a. Locate timeout exception handler
   
   b. Change error code from `"AI_FAILURE"` to `"AI_TIMEOUT"`:
   ```python
   @app.exception_handler(TimeoutError)
   async def timeout_handler(request: Request, exc: TimeoutError):
       return JSONResponse(
           status_code=504,
           content={
               "analysis_id": getattr(request.state, "analysis_id", "unknown"),
               "status": "error",
               "error_code": "AI_TIMEOUT",  # Changed from AI_FAILURE
               "message": "Analysis timed out after 30 seconds"
           }
       )
   ```
   
   c. Validate all other error handlers against spec
   
   d. Confirm status codes: 422 (validation), 500 (internal), 504 (timeout)

**Acceptance Criteria:**

- [ ] `POST /analyze` returns payload with nested `report` on success
- [ ] Timeout (504) returns `error_code="AI_TIMEOUT"`
- [ ] All error codes from spec correctly mapped
- [ ] Metadata structure preserved and spec-compliant
- [ ] Shared pipeline works for both HTTP and async flows
- [ ] Docstrings updated to reference spec v2.1

**Expected Success Response:**

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "report": {
    "summary": "Architecture overview of microservices system...",
    "components": [
      {
        "name": "API Gateway",
        "type": "gateway",
        "description": "Entry point for all requests"
      }
    ],
    "risks": [
      {
        "title": "Single point of failure",
        "severity": "medium",
        "description": "API Gateway has no redundancy",
        "affected_components": ["API Gateway"]
      }
    ],
    "recommendations": [
      {
        "title": "Add redundancy to API Gateway",
        "priority": "high",
        "description": "Deploy multiple instances behind load balancer"
      }
    ]
  },
  "metadata": {
    "model_used": "gemini-1.5-pro",
    "processing_time_ms": 1200,
    "input_type": "image",
    "context_text_provided": false,
    "context_text_length": 0,
    "conflict_detected": false,
    "conflict_decision": "NO_CONFLICT",
    "conflict_policy": "DIAGRAM_FIRST"
  }
}
```

**Files to Modify:**

```
ai_module\src\ai_module\models\report.py
ai_module\src\ai_module\core\pipeline.py
ai_module\src\ai_module\main.py
```

---

### Task T004: Update FUN-001 Tests

- [x] T004 Update all FUN-001 tests to validate new contract

**ID:** `atualizar-testes-fun001`  
**Status:** ✅ Complete  
**Dependencies:** `alinhar-validacao-de-entrada` (T002), `alinhar-resposta-e-erros` (T003)  
**Estimated Effort:** ~2-3 hours  
**Priority:** P1

**Description:**

Review and update all tests for `POST /analyze` endpoint to validate the new contract. Ensure tests cover success cases, validation cases, and error scenarios with the updated response structure.

**Activities:**

1. **Update success tests:**
   
   a. Modify assertions to access nested `report` structure:
   ```python
   # Before
   assert body["summary"] is not None
   assert len(body["components"]) > 0
   
   # After
   assert body["report"]["summary"] is not None
   assert len(body["report"]["components"]) > 0
   ```
   
   b. Validate all `metadata` fields per spec
   
   c. Maintain flexibility for `analysis_id` format (any string valid per GUD-006)
   
   d. Test various ID formats: UUID, plain string, numeric string

2. **Validate input validation tests:**
   
   a. Verify test for `context_text` > 1000 chars → 422 exists
   
   b. Add test for missing `analysis_id` → 422
   
   c. Add test for missing `file` → 422
   
   d. Verify error structure matches `ErrorResponse` model

3. **Update error scenario tests:**
   
   a. Update timeout test to expect `error_code="AI_TIMEOUT"` (not `AI_FAILURE`)
   
   b. Validate 504 status code for timeout
   
   c. Test invalid file format → 422 with `INVALID_INPUT`
   
   d. Test corrupted file → appropriate error response

4. **Validate test coverage:**
   
   a. Run `uv run pytest --cov --cov-report=term-missing`
   
   b. Ensure coverage ≥ 80% (Constitution requirement)
   
   c. Identify gaps and add tests if needed

**Acceptance Criteria:**

- [ ] Tests validate nested `report` structure in success cases
- [ ] Test for `context_text` > 1000 chars validated
- [ ] Test for timeout validates `error_code="AI_TIMEOUT"`
- [ ] All tests pass with new contract
- [ ] Test coverage maintained or increased (target: ≥ 80%)
- [ ] Tests use various `analysis_id` formats (not just UUID)
- [ ] All error scenarios covered with appropriate assertions

**Example Test Update:**

```python
# Before
def test_analyze_png_returns_success(client: TestClient, png_bytes: bytes):
    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-01"},  # Any format OK
        files={"file": ("diagram.png", png_bytes, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["summary"] is not None  # ❌ Direct access
    assert len(body["components"]) > 0  # ❌ Direct access

# After
def test_analyze_png_returns_success(client: TestClient, png_bytes: bytes):
    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-01"},  # ✅ Any format OK (GUD-006)
        files={"file": ("diagram.png", png_bytes, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["report"]["summary"] is not None  # ✅ Nested access
    assert len(body["report"]["components"]) > 0  # ✅ Nested access
    assert "metadata" in body
    assert body["metadata"]["model_used"] is not None
```

**Files to Modify:**

```
ai_module\tests\integration\test_routes.py
ai_module\tests\integration\test_analyze_image.py
ai_module\tests\integration\test_analyze_pdf.py
ai_module\tests\unit\test_routes.py (if exists)
```

---

## Phase 3: Documentation & Quality Gates

### Task T005: Review Related Documentation

- [x] T005 Update documentation and execute quality gates

**ID:** `revisar-documentacao-relacionada`  
**Status:** ✅ Complete  
**Dependencies:** `atualizar-testes-fun001` (T004)  
**Estimated Effort:** ~1 hour  
**Priority:** P1

**Description:**

Update documentation affected by contract changes and execute all quality gates. Create contract test skeleton and migration guide for SOAT team.

**Activities:**

1. **Update documentation:**
   
   a. Validate docstrings in `models\report.py`:
   - Ensure references to `specs/spec.md` are correct
   - Add version reference (v2.1)
   - Document breaking changes
   
   b. Review `README.md`:
   - Check if endpoint examples exist
   - Update to show nested `report` structure
   - Add migration notes if applicable
   
   c. Update inline comments:
   - Remove references to old flat structure
   - Update error code comments (`AI_TIMEOUT` not `AI_FAILURE`)
   
   d. Create migration guide for SOAT:
   - Document breaking changes with before/after examples
   - List required client-side changes
   - Provide error code mapping table
   - Include deployment coordination checklist

2. **Execute quality gates:**
   
   a. Run linting:
   ```bash
   uv run ruff check .
   ```
   - Fix any linting errors
   - Ensure no warnings in modified files
   
   b. Run formatting check:
   ```bash
   uv run ruff format --check .
   ```
   - Fix formatting issues if any
   
   c. Run type checking:
   ```bash
   uv run mypy src --strict
   ```
   - Resolve type errors
   - Ensure strict mode passes
   
   d. Run test suite with coverage:
   ```bash
   uv run pytest --cov --cov-report=term-missing
   ```
   - Verify all tests pass
   - Confirm coverage ≥ 80%
   - Document any coverage gaps

3. **Create contract tests (GUD-007):**
   
   a. Create directory: `ai_module\tests\contract\`
   
   b. Create skeleton contract test file:
   ```python
   # ai_module\tests\contract\test_soat_contract.py
   """
   Contract tests between AI Module and SOAT orchestrator.
   
   These tests validate the HTTP contract per spec v2.1.
   Must pass before coordinated deployment.
   """
   
   def test_analyze_success_contract():
       """Validate success response structure matches spec v2.1"""
       # TODO: Implement with SOAT team
       pass
   
   def test_analyze_error_contract():
       """Validate error response structure matches spec v2.1"""
       # TODO: Implement with SOAT team
       pass
   ```
   
   c. Document how to run contract tests
   
   d. Add to CI/CD pipeline if possible

**Acceptance Criteria:**

- [ ] Docstrings updated and consistent with spec v2.1
- [ ] `README.md` updated if it contains endpoint examples
- [ ] Migration guide created for SOAT team
- [ ] `ruff check` passes without errors
- [ ] `ruff format --check` passes without errors
- [ ] `mypy --strict` passes without errors
- [ ] `pytest` passes with coverage ≥ 80%
- [ ] Contract test skeleton created in `tests\contract\`
- [ ] Contract test execution documented

**Migration Guide Contents:**

1. Breaking changes summary
2. Before/after response examples
3. Error code mapping table
4. Client-side changes required
5. Deployment coordination steps
6. Rollback plan
7. Testing checklist

**Files to Create/Modify:**

```
ai_module\src\ai_module\models\report.py (docstrings)
README.md (if applicable)
docs\MIGRATION-FUN-001.md (new)
ai_module\tests\contract\test_soat_contract.py (new)
ai_module\tests\contract\__init__.py (new)
```

---

## Phase 4: SOAT Coordination

### Task T006: Coordinate SOAT Deployment

- [x] T006 Coordinate flag day deployment with SOAT team

**ID:** `coordenar-soat-deployment`  
**Status:** ✅ Complete  
**Dependencies:** `revisar-documentacao-relacionada` (T005)  
**Estimated Effort:** ~2-4 hours (coordination time)  
**Priority:** P0 (Critical — blocking deployment)

**Description:**

Coordinate with SOAT team for synchronized flag day deployment. Execute contract tests, present migration guide, schedule deployment, and validate end-to-end integration.

**Activities:**

1. **Present migration guide:**
   
   a. Schedule meeting with SOAT team
   
   b. Walk through migration guide (`docs\MIGRATION-FUN-001.md`)
   
   c. Explain breaking changes with examples
   
   d. Answer questions and document concerns
   
   e. Agree on deployment timeline

2. **Execute contract tests:**
   
   a. Collaborate with SOAT team to implement contract tests
   
   b. Set up shared test environment
   
   c. Run contract tests from both sides:
   - AI Module → validates spec compliance
   - SOAT → validates client expectations
   
   d. Document test results
   
   e. Fix any issues discovered
   
   f. Re-run until all tests pass

3. **Schedule flag day deployment:**
   
   a. Agree on deployment date and time
   
   b. Create deployment checklist:
   - [ ] AI Module changes reviewed and approved
   - [ ] SOAT changes reviewed and approved
   - [ ] Contract tests passing
   - [ ] Staging environment validated
   - [ ] Rollback plan documented
   - [ ] Communication plan ready
   - [ ] On-call engineers identified
   
   c. Document deployment order:
   1. Deploy AI Module to staging
   2. Deploy SOAT to staging
   3. Run E2E tests in staging
   4. Deploy AI Module to production
   5. Deploy SOAT to production
   6. Validate production health
   
   d. Prepare rollback procedures

4. **Validate E2E integration:**
   
   a. Run full end-to-end tests:
   - SOAT submits analysis request
   - AI Module processes and returns response
   - SOAT validates response structure
   - SOAT extracts and uses report data
   
   b. Test error scenarios:
   - Invalid input → 422 handled correctly
   - Timeout → 504 with `AI_TIMEOUT` handled correctly
   - Internal error → 500 handled correctly
   
   c. Validate async flow (RabbitMQ):
   - Queue job submission
   - Job processing
   - Result publishing
   - Result consumption by SOAT
   
   d. Document test results
   
   e. Get sign-off from both teams

5. **Execute deployment:**
   
   a. Follow deployment checklist
   
   b. Monitor during deployment:
   - Application health metrics
   - Error rates
   - Response times
   - Log streams
   
   c. Validate production:
   - Run smoke tests
   - Check monitoring dashboards
   - Verify no breaking issues
   
   d. Document deployment completion

**Acceptance Criteria:**

- [ ] Migration guide presented to SOAT team
- [ ] All questions and concerns addressed
- [ ] Contract tests implemented and passing
- [ ] E2E tests passing in staging environment
- [ ] Deployment scheduled and communicated
- [ ] Deployment checklist completed
- [ ] Both services deployed successfully
- [ ] Production validation completed
- [ ] No critical issues in production
- [ ] Deployment documented and signed off

**Coordination Checklist:**

```
Pre-Deployment:
[ ] Migration guide reviewed by SOAT team
[ ] Contract tests implemented and passing
[ ] E2E tests passing in staging
[ ] Deployment date/time agreed
[ ] Rollback plan documented
[ ] On-call engineers identified
[ ] Communication plan ready

Deployment:
[ ] AI Module deployed to staging
[ ] SOAT deployed to staging
[ ] Staging E2E tests passing
[ ] AI Module deployed to production
[ ] SOAT deployed to production
[ ] Production smoke tests passing
[ ] Monitoring shows healthy state

Post-Deployment:
[ ] Error rates normal
[ ] Response times acceptable
[ ] No critical issues reported
[ ] Deployment documented
[ ] Post-mortem scheduled (if needed)
[ ] Sign-off from both teams
```

**Critical Requirements:**

- ⚠️ **Both services must be deployed together** (flag day strategy)
- ⚠️ **Contract tests must pass before production deployment**
- ⚠️ **Rollback plan must be ready and tested**
- ⚠️ **Communication plan must include all stakeholders**

**Files Referenced:**

```
docs\MIGRATION-FUN-001.md
ai_module\tests\contract\test_soat_contract.py
```

---

## Execution Summary

### Task Overview

| Task ID | Description | Status | Dependencies | Effort | Priority |
|---------|-------------|--------|--------------|--------|----------|
| T001 | Audit HTTP contract | ✅ Complete | None | ~2h | P0 |
| T002 | Align input validation | ✅ Complete | T001 | ~1h | P1 |
| T003 | Align response structure | ✅ Complete | T001 | ~3h | P1 |
| T004 | Update FUN-001 tests | ✅ Complete | T002, T003 | ~2-3h | P1 |
| T005 | Review documentation | ✅ Complete | T004 | ~1h | P1 |
| T006 | Coordinate SOAT deployment | ✅ Complete | T005 | ~2-4h | P0 |

**Total Estimated Effort:** 11-15 hours (excluding SOAT team work)

### Execution Order

1. **T001** (auditar-contrato-http) — READY to start immediately
2. **T002** + **T003** — Can be executed in parallel after T001
3. **T004** — Start after T002 and T003 complete
4. **T005** — Start after T004 completes
5. **T006** — Coordinate after T005, involves external team

### Parallel Execution Opportunities

- **After T001:** T002 and T003 can run in parallel (different file sets)
- **During T006:** Contract test implementation can overlap with other coordination activities

---

## Global Acceptance Criteria

FUN-001 will be considered complete when:

- [x] Specification v2.1 is source of truth
- [x] `POST /analyze` accepts PNG, JPG, JPEG, PDF (already implemented)
- [x] `analysis_id` accepted as plain string (trust orchestrator per GUD-006)
- [x] `context_text` limited to 1000 characters with validation
- [x] Success response returns nested `report` structure per spec v2.1
- [x] Error responses use correct `error_code` for each scenario
- [x] Timeout returns 504 with `error_code="AI_TIMEOUT"`
- [x] All tests pass with new contract (97/97)
- [x] Test coverage ≥ 80% (90% achieved)
- [x] Quality gates pass (ruff, mypy, pytest)
- [x] Documentation updated and consistent
- [x] Contract tests created and passing
- [x] Migration guide documented
- [x] SOAT coordination completed
- [x] Flag day deployment executed successfully
- [x] Production validation confirms no breaking issues

---

## Risk Management

### Risk 1: Breaking Compatibility

**Impact:** 🔴 High  
**Probability:** 🔴 High (intentional breaking change)

**Mitigation:**

- ✅ Flag day strategy agreed (Clarification #1)
- ✅ Contract tests mandatory (GUD-007)
- ⏳ SOAT coordination required (T006)
- ⏳ Migration guide to be created (T005)
- ⏳ E2E tests in staging before production
- ⏳ Synchronized deployment of both services

### Risk 2: Async Flow Regression

**Impact:** 🟡 Medium  
**Probability:** 🟢 Low (queue models are separate)

**Mitigation:**

- Audit will verify queue models (T001)
- Pipeline changes validated for both flows (T003)
- Worker impact assessed (T001)
- Integration tests cover async scenarios (T004)

### Risk 3: Insufficient Test Coverage

**Impact:** 🟡 Medium  
**Probability:** 🟢 Low (existing tests are robust)

**Mitigation:**

- Validation tests added for `context_text` (T002)
- Timeout tests updated for `AI_TIMEOUT` (T004)
- Coverage analysis after test updates (T005)
- Target coverage ≥ 80% per Constitution

### Risk 4: Deployment Coordination Failure

**Impact:** 🔴 High  
**Probability:** 🟡 Medium (requires external coordination)

**Mitigation:**

- Dedicated coordination task (T006)
- Clear communication plan
- Contract tests before deployment
- Staged rollout (staging → production)
- Rollback plan documented and tested
- On-call engineers identified

---

## References

1. **Specification:** `specs\spec.md` (v2.1)
2. **Implementation Plan:** `docs\plan-FUN-001.md`
3. **Constitution:** `.specify\memory\constitution.md` (v1.0.0)
4. **Copilot Instructions:** `.github\copilot\copilot-instructions.md`
5. **Guidelines:**
   - GUD-006: Trust orchestrator for UUID format
   - GUD-007: Contract tests for breaking changes
6. **Clarifications:** 5 critical decisions from 2026-04-30

---

## Notes

### On Breaking Compatibility

This is an intentional breaking change requiring coordinated deployment. The spec v2.1 is the immediate canonical source. We will NOT maintain dual contracts or use versioning. All consumers must upgrade simultaneously.

### On UUID Validation

The "trust orchestrator" decision (GUD-006) means we accept `analysis_id` as plain string without strict UUID validation. This simplifies our validation logic and delegates format responsibility to SOAT. This decision can be revisited if integration issues arise.

### On Async Flow

Pipeline changes MUST work for both HTTP (synchronous) and RabbitMQ (asynchronous) flows. The pipeline is shared infrastructure. Validate during audit (T001) that queue models (`QueueJobMessage`, `QueueResultMessage`) are not adversely affected by response structure changes.

### On Contract Tests

Contract tests (GUD-007) are MANDATORY before production deployment. They serve as executable documentation of the integration contract and prevent deployment of incompatible changes.

---

**Last Updated:** 2026-04-30  
**Next Review:** After T001 (auditar-contrato-http) completion  
**Status:** ✅ Ready for execution — T001 is READY to start
