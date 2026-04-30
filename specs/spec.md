---
title: Architecture AI Module Analysis Specification
version: 2.1
date_created: 2026-04-30
last_updated: 2026-04-30
owner: FIAP Hackathon Fase 5 Team
tags:
  - architecture
  - ai-module
  - fastapi
  - rabbitmq
  - multimodal
clarifications:
  - date: 2026-04-30
    issues_resolved:
      - Breaking change strategy (flag day with SOAT)
      - Directory structure standardization (specs/ for specs, docs/ for plans)
      - PDF page count confirmation (3 pages)
      - UUID validation approach (plain string, trust orchestrator)
      - SOAT migration coordination (contract tests required)
---

# Introduction

This specification defines the functional, technical, operational, and quality requirements for the AI module responsible for analyzing architecture diagrams and producing a structured technical report.

The document is optimized for Generative AI consumption. It is self-contained, explicit, and organized around requirements, constraints, interfaces, and acceptance criteria.

## 1. Purpose & Scope

This specification applies to the `ai_module` service in this repository.

Purpose:

1. Receive architecture diagrams through a synchronous HTTP API or an asynchronous RabbitMQ workflow.
2. Execute multimodal analysis using a configurable Large Language Model (LLM) provider.
3. Return a validated, structured JSON report suitable for downstream systems.
4. Expose operational health and metrics for monitoring.

In scope:

1. File validation and preprocessing for PNG, JPG, JPEG, and PDF inputs.
2. Prompt construction with optional contextual text.
3. Multimodal LLM invocation through provider adapters.
4. Strict response validation against a predefined report schema.
5. Structured error handling for HTTP and queue workflows.
6. Observability through logs, metrics, and health endpoints.

Out of scope:

1. Persistence of reports or analysis lifecycle state.
2. Authentication and authorization inside this service.
3. Direct user-facing orchestration logic.
4. Support for file formats other than PNG, JPG, JPEG, and PDF.
5. Analysis of PDF pages beyond the first three pages.

Audience:

1. Engineers implementing or changing `ai_module`.
2. Engineers integrating this module with the SOAT orchestrator.
3. AI agents generating code, tests, or design updates for this repository.

Assumptions:

1. Access control is handled upstream by SOAT or an API Gateway.
2. The service runs on Python 3.11-compatible environments.
3. The service may call external LLM providers over HTTPS.

## 2. Definitions

| Term | Definition |
|---|---|
| AI Module | The FastAPI microservice in `ai_module` that analyzes architecture diagrams. |
| SOAT | The orchestrator system that submits analysis requests and consumes results. |
| LLM | Large Language Model used for multimodal diagram analysis. |
| Adapter | Provider-specific integration layer implementing the common LLM contract. |
| Report | Structured output containing summary, components, risks, and recommendations. |
| `context_text` | Optional auxiliary text supplied with the request. It may enrich naming but must never override visual evidence. |
| DIAGRAM_FIRST | Conflict-resolution policy where diagram evidence has precedence over `context_text`. |
| Worker | The asynchronous RabbitMQ consumer/publisher flow running in the same service. |
| DLQ | Dead Letter Queue used for irrecoverable malformed queue messages. |
| Health endpoint | `GET /health`, used by operators to detect healthy or degraded state. |
| Metrics endpoint | `GET /metrics`, used to expose Prometheus-compatible metrics. |

## 3. Requirements, Constraints & Guidelines

### Functional Requirements

- **FUN-001**: The system MUST expose `POST /analyze` to process a single diagram synchronously.
- **FUN-002**: The system MUST accept `file` and `analysis_id` as required inputs for synchronous analysis.
- **FUN-003**: The system MUST support `context_text` as an optional input with a maximum length of 1000 characters.
- **FUN-004**: The system MUST support PNG, JPG, JPEG, and PDF files.
- **FUN-005**: The system MUST detect the real file type using magic bytes and MUST NOT trust the file extension alone.
- **FUN-006**: The system MUST validate the LLM output against a strict report schema before returning success.
- **FUN-007**: The system MUST expose `GET /health`.
- **FUN-008**: The system MUST expose `GET /metrics`.
- **FUN-009**: The system MUST consume asynchronous jobs from `analysis.requests`.
- **FUN-010**: The system MUST publish asynchronous results to `analysis.results`.

### Architectural Patterns

- **PAT-001**: The service MUST preserve repository boundaries between `api`, `core`, `adapters`, and `models`.
- **PAT-002**: Route handlers MUST remain thin and delegate business logic to `core`.
- **PAT-003**: Provider-specific SDK calls MUST remain inside adapter implementations.
- **PAT-004**: Shared pipeline behavior MUST be reused by both the HTTP flow and the RabbitMQ worker.
- **PAT-005**: Domain exceptions MUST be mapped to structured HTTP or queue error outputs.

### Data and Validation Requirements

- **DAT-001**: `analysis_id` MUST be a UUID-compatible identifier supplied by the orchestrator.
- **DAT-002**: `context_text` MUST be isolated in the prompt and treated as auxiliary data only.
- **DAT-003**: The report schema MUST contain `summary`, `components`, `risks`, and `recommendations`.
- **DAT-004**: `components` MUST contain at least one item in successful responses.
- **DAT-005**: Enum values outside the allowed range MUST be normalized according to repository rules.
- **DAT-006**: Internal LLM conflict metadata MAY be processed internally but MUST NOT be exposed as a raw internal field in the final response.

### Error Handling Requirements

- **ERR-001**: Invalid file content or unsupported formats MUST return structured validation errors.
- **ERR-002**: LLM timeouts MUST fail explicitly and MUST NOT retry indefinitely.
- **ERR-003**: Schema-invalid LLM responses MUST trigger bounded retry behavior.
- **ERR-004**: Malformed queue messages MUST be rejected without calling the analysis pipeline.
- **ERR-005**: Failures to publish queue results MUST be surfaced explicitly so the message can be retried according to queue policy.

### Security Requirements

- **SEC-001**: The service MUST reject unsupported or malformed file inputs before analysis.
- **SEC-002**: The service MUST enforce request boundary validation for all public inputs.
- **SEC-003**: The service MUST NOT log file bytes, raw binary payloads, API keys, or literal `context_text`.
- **SEC-004**: The service MUST include security headers on HTTP responses.
- **SEC-005**: The service MUST assume authentication is external and MUST NOT introduce internal auth logic unless explicitly required.

### Observability Requirements

- **OBS-001**: The service MUST emit structured logs with semantic event names.
- **OBS-002**: The service MUST expose Prometheus-compatible metrics.
- **OBS-003**: The health endpoint MUST indicate healthy or degraded status.
- **OBS-004**: Retry, queue, and analysis outcomes MUST be observable through logs and metrics.

### Performance Requirements

- **PER-001**: The service MUST enforce input-size limits before expensive processing when feasible.
- **PER-002**: Images larger than the configured processing threshold MUST be downsampled while preserving aspect ratio.
- **PER-003**: PDF analysis MUST be limited to the first three pages. (Clarified 2026-04-30: This is an intentional upgrade from the initial 1-page support.)
- **PER-004**: Retry behavior MUST be bounded by configured timeout and retry limits.
- **PER-005**: Performance-sensitive failures MUST fail fast and explicitly rather than degrade silently.

### Constraints

- **CON-001**: The implementation MUST remain compatible with Python 3.11.
- **CON-002**: The implementation MUST use Pydantic v2 APIs and strict model validation patterns already used in the repository.
- **CON-003**: The implementation MUST remain compatible with the repository's documented FastAPI and pytest conventions.
- **CON-004**: The service MUST not persist report data.
- **CON-005**: The service MUST not analyze PDF pages beyond page three.

### Guidelines

- **GUD-001**: Prefer explicit, typed contracts over inferred structures.
- **GUD-002**: Update external-facing documentation whenever request, response, runtime, or operational behavior changes.
- **GUD-003**: Reuse existing validators, settings, metrics, and logging helpers instead of duplicating logic.
- **GUD-004**: Keep the specification aligned with the repository constitution in `.specify\memory\constitution.md`.
- **GUD-005**: Specifications MUST be stored in `specs/` directory; implementation plans MUST be stored in `docs/` directory.
- **GUD-006**: The `analysis_id` field is a plain string identifier provided by the orchestrator. Validation is delegated to the orchestrator; this service trusts the provided value.
- **GUD-007**: Breaking changes to public contracts MUST be coordinated with SOAT team via flag day deployment. Contract tests MUST be added between services before deployment.

## 4. Interfaces & Data Contracts

### 4.1 HTTP Interface

#### Endpoint: `POST /analyze`

**Request**

| Field | Type | Required | Rules |
|---|---|---|---|
| `file` | multipart file | Yes | Must be PNG, JPG, JPEG, or PDF by magic bytes and size rules |
| `analysis_id` | string | Yes | Traceable identifier from orchestrator |
| `context_text` | string | No | Maximum 1000 characters |

**Success Response**

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "report": {
    "summary": "The diagram shows an API gateway, application services, a message queue, and a database.",
    "components": [
      {
        "name": "API Gateway",
        "type": "gateway",
        "description": "Entry point for client requests."
      }
    ],
    "risks": [
      {
        "title": "Single point of failure in gateway",
        "severity": "medium",
        "description": "The gateway appears to be deployed without redundant instances.",
        "affected_components": ["API Gateway"]
      }
    ],
    "recommendations": [
      {
        "title": "Add gateway redundancy",
        "priority": "high",
        "description": "Deploy multiple instances behind a load balancer."
      }
    ]
  },
  "metadata": {
    "model_used": "string",
    "processing_time_ms": 1200,
    "input_type": "image",
    "context_text_provided": true,
    "context_text_length": 128,
    "downsampling_applied": false,
    "conflict_detected": false,
    "conflict_decision": "NO_CONFLICT",
    "conflict_policy": "DIAGRAM_FIRST"
  }
}
```

**Error Response**

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "error",
  "error_code": "INVALID_INPUT",
  "message": "Descrição legível do erro"
}
```

**Error Codes**

| Error Code | Meaning |
|---|---|
| `INVALID_INPUT` | Invalid request content, invalid file, or invalid field values |
| `UNSUPPORTED_FORMAT` | Unsupported file type detected by validation |
| `AI_FAILURE` | LLM processing failed after allowed retries or non-retryable provider failure |
| `AI_TIMEOUT` | LLM call exceeded timeout |
| `UPSTREAM_OVERLOAD` | Upstream provider overload or rate limiting condition |
| `INTERNAL_ERROR` | Unexpected server-side failure |

#### Endpoint: `GET /health`

**Healthy Response**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "llm_provider": "GEMINI"
}
```

**Degraded Response**

```json
{
  "status": "degraded",
  "version": "0.1.0",
  "llm_provider": "GEMINI"
}
```

#### Endpoint: `GET /metrics`

The endpoint MUST expose Prometheus text format including request, retry, provider, queue, and timing metrics.

### 4.2 RabbitMQ Interfaces

#### Input Queue: `analysis.requests`

| Property | Value |
|---|---|
| Exchange | `analysis` |
| Exchange Type | `direct` |
| Routing Key | `requests` |
| Consumer Behavior | Single-message prefetch recommended |

**Request Message**

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_bytes_b64": "base64-encoded-string",
  "file_name": "diagram.png",
  "context_text": "texto opcional"
}
```

#### Output Queue: `analysis.results`

| Property | Value |
|---|---|
| Exchange | `analysis` |
| Exchange Type | `direct` |
| Routing Key | `results` |
| Message Durability | Persistent |
| Content Type | `application/json` |

**Success Result Message**

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "report": {
    "summary": "Resumo técnico",
    "components": [],
    "risks": [],
    "recommendations": []
  },
  "metadata": {
    "model_used": "string",
    "processing_time_ms": 1200,
    "input_type": "pdf",
    "context_text_provided": false,
    "context_text_length": 0,
    "downsampling_applied": false,
    "conflict_detected": false,
    "conflict_decision": "NO_CONFLICT",
    "conflict_policy": "DIAGRAM_FIRST"
  }
}
```

**Error Result Message**

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "error",
  "error_code": "AI_FAILURE",
  "message": "Descrição legível do erro"
}
```

### 4.3 Report Data Contract

#### Report Schema

| Field | Type | Rules |
|---|---|---|
| `summary` | string | Non-empty, maximum 500 characters after normalization |
| `components` | array | Minimum length 1 |
| `risks` | array | May be empty |
| `recommendations` | array | May be empty |

#### Component Contract

| Field | Type | Rules |
|---|---|---|
| `name` | string | Required |
| `type` | enum | `service`, `database`, `queue`, `gateway`, `cache`, `external`, `unknown` |
| `description` | string | Required |

#### Risk Contract

| Field | Type | Rules |
|---|---|---|
| `title` | string | Required |
| `severity` | enum | `high`, `medium`, `low` |
| `description` | string | Required |
| `affected_components` | array of string | May be empty; invalid references may be normalized out |

#### Recommendation Contract

| Field | Type | Rules |
|---|---|---|
| `title` | string | Required |
| `priority` | enum | `high`, `medium`, `low` |
| `description` | string | Required |

### 4.4 Processing Flow Contract

The common pipeline MUST perform the following ordered stages:

1. Validate input type and size.
2. Normalize image or extract up to three PDF pages.
3. Build prompts, including schema injection and isolated `context_text`.
4. Invoke the configured LLM adapter with timeout control.
5. Parse, normalize, and validate structured output.
6. Detect and apply DIAGRAM_FIRST conflict policy metadata.
7. Return a structured result for HTTP or queue publication.

## 5. Acceptance Criteria

- **AC-001**: Given a valid PNG, JPG, JPEG, or PDF and a valid `analysis_id`, when `POST /analyze` is called, then the system shall return `200` with a valid `AnalysisResponse` containing a valid `report`.
- **AC-002**: Given a file that exceeds configured size or fails magic-byte validation, when `POST /analyze` is called, then the system shall return `422` with a structured error response.
- **AC-003**: Given `context_text` longer than 1000 characters, when `POST /analyze` is called, then the system shall reject the request with `422`.
- **AC-004**: Given a provider timeout, when synchronous analysis is running, then the system shall return `504` with `error_code` equal to `AI_TIMEOUT`.
- **AC-005**: Given repeated schema-invalid LLM responses until retry exhaustion, when analysis is running, then the system shall return or publish an `AI_FAILURE` error outcome.
- **AC-006**: Given a valid queue message on `analysis.requests`, when the worker consumes the message, then it shall execute the common pipeline and publish one result message on `analysis.results`.
- **AC-007**: Given malformed queue JSON or missing required queue fields, when the worker consumes the message, then it shall reject the message without calling the analysis pipeline.
- **AC-008**: Given a successful startup state, when `GET /health` is called, then the system shall return `200` and `status` equal to `healthy`.
- **AC-009**: Given degraded startup or unrecoverable RabbitMQ connectivity failure, when `GET /health` is called, then the system shall return `503` and `status` equal to `degraded`.
- **AC-010**: Given any successful analysis result, when the output report is returned, then `components` shall contain at least one item.
- **AC-011**: Given a conflict between `context_text` and visible diagram evidence, when the pipeline detects the conflict, then the final outcome shall preserve diagram evidence and report conflict metadata using DIAGRAM_FIRST semantics.
- **AC-012**: Given an input image larger than the configured processing threshold, when preprocessing occurs, then the service shall downsample the image and mark `downsampling_applied` as `true`.
- **AC-013**: Given a PDF with more than three pages, when preprocessing occurs, then only the first three pages shall be analyzed and the request shall not fail solely because extra pages exist.
- **AC-014**: Given `GET /metrics`, when the endpoint is called, then the system shall return Prometheus-compatible metrics for request outcomes, retries, queue activity, and processing time.

## 6. Test Automation Strategy

- **Test Levels**: Unit and integration tests are mandatory. End-to-end validation is recommended when queue infrastructure is available.
- **Frameworks**: `pytest`, `pytest-asyncio`, and `pytest-cov`.
- **Static Quality Gates**: `ruff` and `mypy`.
- **Async Testing**: Async behavior MUST use the repository's pytest async conventions.
- **Test Data Management**: Use fixtures from `tests/conftest.py` and mock LLM providers rather than calling external services.
- **Queue Testing**: Use mocks or isolated integration wiring to verify `ack`, `nack`, and publication behavior.
- **Regression Testing**: Bug fixes MUST include regression coverage when the behavior is testable.
- **CI/CD Integration**: The standard automated verification flow for code changes is `ruff`, `mypy`, and `pytest`.
- **Coverage Requirements**: Coverage should remain aligned with the repository's documented target of 80%.
- **Performance Testing**: At minimum, validate timeout, retry, downsampling, and multi-page PDF edge behavior in automation.

Recommended automation scenarios:

1. Valid synchronous analysis request.
2. Invalid magic bytes and invalid file-size request.
3. `context_text` length rejection.
4. Schema-invalid LLM response with retry exhaustion.
5. LLM timeout without infinite retry behavior.
6. Queue message success path.
7. Queue malformed message rejection path.
8. Queue publish failure retry path.
9. Health healthy and degraded responses.
10. Metrics endpoint serialization.

## 7. Rationale & Context

The AI module exists to replace slow and inconsistent manual analysis of architecture diagrams with a repeatable machine-readable workflow.

Key design rationale:

1. A shared core pipeline prevents divergence between REST and RabbitMQ behaviors.
2. Adapter-based LLM integration isolates provider SDK differences and supports provider switching through configuration.
3. Strict schema validation is required because LLM output is probabilistic and must be normalized before downstream use.
4. DIAGRAM_FIRST is necessary because contextual text is supplementary and must not override visible evidence from the diagram.
5. Health and metrics are required because operators must monitor the service without direct log access.
6. Input validation and fail-fast limits protect the service from malformed data, oversized inputs, and avoidable resource waste.

## 8. Dependencies & External Integrations

### External Systems

- **EXT-001**: SOAT orchestrator - submits HTTP requests and/or queue jobs and consumes structured results.

### Third-Party Services

- **SVC-001**: Configurable LLM provider - must support multimodal analysis and structured text output.

### Infrastructure Dependencies

- **INF-001**: RabbitMQ - required for asynchronous request consumption and result publication.
- **INF-002**: Container runtime - required for local and deployment execution through Docker-compatible workflows.

### Data Dependencies

- **DAT-101**: Diagram file payload - binary image or PDF content supplied by the orchestrator.
- **DAT-102**: Optional contextual text - plain text with a strict maximum size.

### Technology Platform Dependencies

- **PLT-001**: Python 3.11-compatible runtime.
- **PLT-002**: FastAPI-compatible ASGI execution environment.
- **PLT-003**: Pydantic v2-compatible validation model patterns.

### Compliance Dependencies

- **COM-001**: Secrets management discipline - credentials must be supplied externally and never hardcoded.
- **COM-002**: Internal network exposure assumptions - the service depends on upstream access control and network isolation.

## 9. Examples & Edge Cases

### Example: Valid Synchronous Request

```http
POST /analyze
Content-Type: multipart/form-data

file=<diagram.pdf>
analysis_id=550e8400-e29b-41d4-a716-446655440000
context_text=Sistema com gateway e fila de mensagens
```

### Example: Queue Request Message

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_bytes_b64": "JVBERi0xLjQKJ...",
  "file_name": "diagram.pdf",
  "context_text": "Arquitetura com microsserviços"
}
```

### Edge Cases

```text
1. File extension says ".png" but magic bytes indicate PDF -> reject as unsupported or invalid according to validation rules.
2. PDF has five pages -> analyze only the first three pages.
3. Image exceeds processing dimensions -> downsample and record metadata.
4. context_text conflicts with visible diagram -> preserve diagram evidence and mark conflict metadata.
5. LLM returns markdown-wrapped JSON -> sanitize and validate before accepting.
6. LLM returns unknown enum values -> normalize according to repository rules.
7. Queue message is malformed JSON -> reject without calling the pipeline.
8. RabbitMQ output publication fails -> surface failure and allow queue retry behavior.
```

## 10. Validation Criteria

The specification is considered satisfied only when all of the following are true:

1. Public interfaces conform to the contracts in Section 4.
2. All acceptance criteria in Section 5 are demonstrably satisfied.
3. Automated tests cover the mandatory behaviors in Section 6.
4. Validation, logging, and error handling remain explicit and structured.
5. Health and metrics endpoints remain operational and meaningful.
6. HTTP and RabbitMQ paths share the same core analysis semantics.
7. Security, performance, and architectural constraints from Section 3 are preserved.
8. Documentation stays consistent with externally visible behavior.

## 11. Related Specifications / Further Reading

1. `README.md`
2. `.github\copilot\copilot-instructions.md`
3. `.specify\memory\constitution.md`
4. `ai_module\pyproject.toml`
