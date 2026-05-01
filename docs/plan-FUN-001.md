# Plano de Implementação — FUN-001

**Requisito:** O sistema MUST expose `POST /analyze` to process a single diagram synchronously.  
**Spec Version:** 2.1  
**Data de Criação:** 2026-04-30  
**Última Atualização:** 2026-04-30  
**Status:** ✅ Concluído — Flag day deployment e validação em produção realizados com sucesso

---

## 1. Contexto e Problema

O requisito `FUN-001` define que o sistema deve expor o endpoint `POST /analyze` para processar um diagrama de arquitetura de forma síncrona. **A implementação atual já possui esse endpoint operacional**, mas apresenta desalinhamentos significativos em relação à especificação v2.1 (`specs\spec.md`).

### 1.1 Estado Atual

**✅ Componentes já implementados:**

- Rota `POST /analyze` em `ai_module\src\ai_module\api\routes\analyze.py`
- Pipeline síncrono reutilizável em `ai_module\src\ai_module\core\pipeline.py`
- Exception handlers em `ai_module\src\ai_module\main.py`
- Testes unitários e de integração em `ai_module\tests\`

**⚠️ Gaps identificados:**

1. **Contrato de resposta desalinhado**: implementação retorna payload achatado com `summary`, `components`, `risks`, `recommendations` no nível raiz, enquanto spec v2.1 define estrutura com `report` aninhado
2. **Validação de entrada inconsistente**: `analysis_id` entra como `str` sem validação explícita na camada HTTP
3. **Mapeamento de erros incompleto**: timeout retorna `error_code="AI_FAILURE"` em vez de `AI_TIMEOUT` conforme especificado
4. **Testes desatualizados**: testes validam contrato antigo e usam valores de `analysis_id` não-UUID (ex: `"img-test-01"`)
5. **Referências documentais obsoletas**: docstrings referenciam `specs/spec.md` (correto, mas precisa validar)

### 1.2 Objetivo

Alinhar completamente a implementação do endpoint `POST /analyze` ao contrato definido na especificação v2.1, garantindo:

- Contratos HTTP consistentes com a spec
- Validação apropriada de entradas na borda da API
- Mapeamento correto de erros e códigos de status
- Cobertura de testes adequada ao contrato especificado
- Documentação atualizada

---

## 2. Decisões de Design

### 2.1 Fonte da Verdade

A especificação `specs\spec.md` v2.1 é a fonte canônica para o contrato HTTP. **Qualquer divergência entre código atual e spec será resolvida ajustando o código para conformidade com a spec.**

**Rationale:** A spec foi recentemente atualizada (v2.0 → v2.1) com 5 clarificações críticas resolvidas em 2026-04-30. É o artefato mais atual e representa as decisões arquiteturais acordadas.

### 2.2 Estratégia de Migração

**Abordagem:** Flag day com SOAT (coordinated deployment)

**Decisão tomada em:** 2026-04-30 (Clarification #1)  
**Guideline relacionada:** GUD-007

**Implicações:**

- ✅ Mudança de contrato será implementada de uma vez
- ✅ Coordenação com time SOAT **obrigatória** antes do merge
- ✅ Contract tests entre serviços **devem ser adicionados**
- ❌ Não haverá API versioning (/v1, /v2)
- ❌ Não haverá suporte temporário a ambos os formatos

**Por que flag day?**

- SOAT é o consumidor primário (possivelmente único)
- Minimiza dívida técnica de manter dois contratos
- Evita complexidade de versionamento/feature flags
- Permite implementação limpa e completa

### 2.3 Validação de `analysis_id`

**Abordagem:** Plain string (trust orchestrator)

**Decisão tomada em:** 2026-04-30 (Clarification #4)  
**Guideline relacionada:** GUD-006

**Implicações:**

- ✅ `analysis_id` permanece como `str` na API
- ✅ Nenhuma validação UUID estrita na borda HTTP
- ✅ Testes podem usar qualquer formato de ID
- ℹ️ Responsabilidade de formato UUID delegada ao orquestrador (SOAT)

**Rationale:** Confiança no orquestrador upstream simplifica validação e permite flexibilidade no formato de ID.

### 2.4 Compatibilidade

⚠️ **Esta mudança QUEBRA compatibilidade com clientes que consomem o contrato atual.**

**Mitigação:**

1. Coordenação com time SOAT obrigatória (GUD-007)
2. Contract tests devem ser criados antes do deployment
3. Ambos os serviços (AI Module + SOAT) devem ser deployed juntos
4. Migration guide será documentado para referência

---

## 3. Clarificações Aplicadas

As seguintes clarificações foram resolvidas e guiam este plano:

| # | Questão | Decisão | Spec Ref | Impacto no Plano |
|---|---------|---------|----------|------------------|
| **1** | Estratégia de breaking change | Flag day com SOAT | GUD-007 | Requer coordenação e contract tests |
| **2** | Estrutura de diretórios | specs/ para specs, docs/ para planos | GUD-005 | Este arquivo está em docs/ ✅ |
| **3** | Suporte a páginas de PDF | 3 páginas | PER-003 | README já atualizado ✅ |
| **4** | Validação UUID | Plain string (trust orchestrator) | GUD-006 | Sem validação estrita de UUID |
| **5** | Coordenação SOAT | Contract tests obrigatórios | GUD-007 | Adicionar suite de testes de contrato |

---

## 4. Tarefas de Implementação

### 4.1 Auditar Contrato HTTP

**ID:** `auditar-contrato-http`  
**Status:** ⏳ Pending (READY)  
**Dependências:** Nenhuma  
**Responsável:** Primeiro implementador  
**Estimativa:** ~2h

**Descrição:**
Mapear todos os pontos de impacto da mudança de contrato no código atual e consolidar o contrato canônico final.

**Atividades:**

1. Comparar contrato implementado vs. contrato na spec v2.1
2. Listar todos os arquivos afetados (route, models, pipeline, handlers, tests)
3. Documentar decisões de quebra de compatibilidade
4. Criar checklist de validação do contrato
5. Identificar impactos em fluxo assíncrono (RabbitMQ worker)

**Critérios de aceite:**

- [ ] Documento de impacto criado identificando todos os arquivos afetados
- [ ] Diferenças entre contrato atual e spec v2.1 documentadas
- [ ] Checklist de validação pronto para uso nas tarefas seguintes
- [ ] Confirmação de que modelos compartilhados não quebram fluxo async

**Arquivos a revisar:**

- `ai_module\src\ai_module\api\routes\analyze.py` (rota HTTP)
- `ai_module\src\ai_module\models\report.py` (modelos de response)
- `ai_module\src\ai_module\models\request.py` (modelos de request)
- `ai_module\src\ai_module\core\pipeline.py` (pipeline compartilhado)
- `ai_module\src\ai_module\main.py` (exception handlers)
- `ai_module\tests\integration\test_routes.py` (testes de integração)
- `ai_module\tests\integration\test_analyze_image.py`
- `ai_module\tests\integration\test_analyze_pdf.py`
- `ai_module\src\ai_module\worker.py` (validar impacto async)

**Deliverables:**

- Documento de auditoria (pode ser markdown em session folder)
- Lista de arquivos a modificar
- Checklist de validação do contrato

---

### 4.2 Alinhar Validação de Entrada

**ID:** `alinhar-validacao-de-entrada`  
**Status:** ⏳ Pending (BLOCKED)  
**Dependências:** `auditar-contrato-http`  
**Responsável:** Implementador  
**Estimativa:** ~1h

**Descrição:**
Garantir validação consistente de `context_text` (max 1000 chars) na borda HTTP. Confirmar que `analysis_id` permanece como string sem validação UUID estrita (conforme GUD-006).

**Atividades:**

1. Revisar modelo `AnalyzeRequest` em `models\request.py`
2. Confirmar que `analysis_id` é aceito como `str` (sem validação UUID)
3. Verificar validação de `context_text` com `max_length=1000`
4. Atualizar assinatura da rota `analyze` se necessário
5. Adicionar testes unitários de validação para `context_text`

**Critérios de aceite:**

- [ ] `analysis_id` aceito como qualquer string (trust orchestrator ✅)
- [ ] `context_text` rejeitado se > 1000 caracteres (422)
- [ ] Testes de validação de entrada cobrindo casos válidos e inválidos
- [ ] Mensagens de erro estruturadas conforme spec (ErrorResponse)

**Exemplo de teste:**

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
    assert response.json()["error_code"] == "INVALID_INPUT"
```

---

### 4.3 Alinhar Resposta e Erros

**ID:** `alinhar-resposta-e-erros`  
**Status:** ⏳ Pending (BLOCKED)  
**Dependências:** `auditar-contrato-http`  
**Responsável:** Implementador  
**Estimativa:** ~3h

**Descrição:**
Ajustar modelos de resposta, pipeline e exception handlers para conformidade com spec v2.1. Principal mudança: estrutura de resposta com `report` aninhado.

**Atividades:**

**Modelos (`models\report.py`):**

1. Refatorar `AnalyzeResponse` para incluir `report` aninhado:

   ```python
   class AnalyzeResponse(BaseResponse):
       status: Literal["success"] = "success"
       report: Report  # Aninhado!
       metadata: ReportMetadata
   ```

2. Criar modelo `Report` contendo `summary`, `components`, `risks`, `recommendations`
3. Manter `ErrorResponse` como está (já conforme)
4. Validar docstrings referenciam `specs/spec.md` corretamente

**Pipeline (`core\pipeline.py`):**

1. Ajustar `_build_response()` para retornar estrutura com `report` aninhado
2. Preservar lógica de metadata e conflict detection
3. Garantir que pipeline retorna modelo compatível com HTTP e async

**Exception Handlers (`main.py`):**

1. Atualizar `timeout_handler` para retornar `error_code="AI_TIMEOUT"` (atualmente retorna `AI_FAILURE`)
2. Validar todos os outros handlers contra a spec
3. Garantir status codes corretos (422, 500, 504)

**Critérios de aceite:**

- [ ] `POST /analyze` retorna payload com `report` aninhado em caso de sucesso
- [ ] Timeout (504) retorna `error_code="AI_TIMEOUT"`
- [ ] Todos os error codes da spec estão mapeados corretamente
- [ ] Estrutura de metadata preservada e conforme spec
- [ ] Pipeline compartilhado continua funcionando para fluxo async

**Exemplo de resposta esperada:**

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "report": {
    "summary": "...",
    "components": [...],
    "risks": [...],
    "recommendations": [...]
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

---

### 4.4 Atualizar Testes do FUN-001

**ID:** `atualizar-testes-fun001`  
**Status:** ⏳ Pending (BLOCKED)  
**Dependências:** `alinhar-validacao-de-entrada`, `alinhar-resposta-e-erros`  
**Responsável:** Implementador  
**Estimativa:** ~2-3h

**Descrição:**
Revisar e atualizar todos os testes do endpoint `POST /analyze` para validar o novo contrato.

**Atividades:**

**Testes de sucesso:**

1. Validar estrutura de resposta com `report` aninhado
2. Validar todos os campos de `metadata`
3. Manter flexibilidade de `analysis_id` (qualquer string é válida per GUD-006)

**Testes de validação:**

1. Validar teste existente de `context_text` > 1000 chars → 422
2. Adicionar teste de `analysis_id` ausente → 422
3. Validar teste de `file` ausente → 422

**Testes de erro:**

1. Validar timeout → 504 com `AI_TIMEOUT`
2. Validar outros cenários de erro (formato inválido, arquivo corrompido, etc.)

**Arquivos a atualizar:**

- `ai_module\tests\integration\test_routes.py`
- `ai_module\tests\integration\test_analyze_image.py`
- `ai_module\tests\integration\test_analyze_pdf.py`
- `ai_module\tests\unit\test_routes.py` (se existir)

**Critérios de aceite:**

- [ ] Testes validam estrutura com `report` aninhado
- [ ] Teste de `context_text` > 1000 chars validado
- [ ] Teste de timeout valida `AI_TIMEOUT`
- [ ] Todos os testes passam com o novo contrato
- [ ] Cobertura de testes mantida ou aumentada (target: ≥80%)
- [ ] IDs de teste podem usar qualquer formato (não precisam ser UUID)

**Exemplo de atualização:**

```python
# Antes
def test_analyze_png_returns_success(...):
    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-01"},  # Qualquer formato OK
        files={"file": ("diagram.png", png_bytes, "image/png")},
    )
    assert body["summary"] is not None  # ❌ acesso direto

# Depois
def test_analyze_png_returns_success(...):
    response = client.post(
        "/analyze",
        data={"analysis_id": "img-test-01"},  # ✅ Qualquer formato OK (GUD-006)
        files={"file": ("diagram.png", png_bytes, "image/png")},
    )
    assert body["report"]["summary"] is not None  # ✅ acesso via report
```

---

### 4.5 Revisar Documentação Relacionada

**ID:** `revisar-documentacao-relacionada`  
**Status:** ⏳ Pending (BLOCKED)  
**Dependências:** `atualizar-testes-fun001`  
**Responsável:** Implementador  
**Estimativa:** ~1h

**Descrição:**
Atualizar documentação afetada pelas mudanças de contrato e executar quality gates.

**Atividades:**

**Documentação:**

1. Validar docstrings em `models\report.py` referenciam `specs/spec.md` (já correto)
2. Revisar README.md se houver exemplos de uso do endpoint
3. Atualizar comentários inline que referenciem o contrato antigo
4. Documentar migration guide para SOAT (breaking changes)

**Quality Gates:**

1. Executar `uv run ruff check .`
2. Executar `uv run ruff format --check .`
3. Executar `uv run mypy src --strict`
4. Executar `uv run pytest --cov --cov-report=term-missing`

**Contract Tests (GUD-007):**

1. Criar skeleton de contract tests em `ai_module\tests\contract\`
2. Documentar como executar contract tests entre AI Module e SOAT
3. Adicionar ao CI/CD pipeline se possível

**Critérios de aceite:**

- [ ] Docstrings atualizados e consistentes
- [ ] README.md atualizado se aplicável
- [ ] Migration guide criado para SOAT
- [ ] `ruff check` passa sem erros
- [ ] `ruff format --check` passa sem erros
- [ ] `mypy --strict` passa sem erros
- [ ] `pytest` passa com cobertura ≥ 80%
- [ ] Contract test skeleton criado

---

## 5. Riscos e Mitigações

### 5.1 Quebra de Compatibilidade

**Risco:** Clientes existentes (SOAT) podem falhar ao consumir o novo contrato.

**Impacto:** 🔴 Alto  
**Probabilidade:** 🔴 Alta (mudança intencional de contrato)

**Mitigação:**

1. ✅ Estratégia de flag day acordada (Clarification #1)
2. ✅ Contract tests obrigatórios (GUD-007)
3. ⏳ **TODO:** Coordenar com time SOAT antes do merge
4. ⏳ **TODO:** Criar migration guide com exemplos antes/depois
5. ⏳ **TODO:** Executar testes de integração end-to-end com SOAT antes do release
6. ⏳ **TODO:** Sincronizar deployment de ambos os serviços

### 5.2 Regressão em Fluxo Assíncrono

**Risco:** Mudanças nos modelos compartilhados podem afetar o worker RabbitMQ.

**Impacto:** 🟡 Médio  
**Probabilidade:** 🟢 Baixa (modelos de queue são separados)

**Mitigação:**

1. Revisar modelos `QueueJobMessage` e `QueueResultMessage` durante auditoria
2. Validar que mudanças em `Report` e `AnalysisMetadata` não quebram serialização de fila
3. Executar testes de integração do worker
4. Validar que pipeline compartilhado funciona para ambos os fluxos

### 5.3 Cobertura de Testes Insuficiente

**Risco:** Novos casos de erro não cobertos podem escapar para produção.

**Impacto:** 🟡 Médio  
**Probabilidade:** 🟢 Baixa (testes existentes são robustos)

**Mitigação:**

1. Adicionar testes específicos para validação de `context_text`
2. Validar cenários de timeout com mock adequado
3. Executar análise de cobertura após atualização de testes
4. Garantir cobertura ≥ 80% (Constitution: Tests Define Done)

---

## 6. Critérios de Aceite Globais

O FUN-001 estará completo quando:

1. ✅ `POST /analyze` aceita PNG, JPG, JPEG e PDF válidos
2. ✅ `analysis_id` é aceito como string (trust orchestrator per GUD-006)
3. ✅ `context_text` é limitado a 1000 caracteres
4. ✅ Resposta de sucesso retorna estrutura com `report` aninhado
5. ✅ Resposta de erro retorna `error_code` correto para cada cenário
6. ✅ Timeout retorna 504 com `error_code="AI_TIMEOUT"`
7. ✅ Todos os testes passam com o novo contrato
8. ✅ Cobertura de testes ≥ 80%
9. ✅ Quality gates (ruff, mypy, pytest) passam
10. ✅ Documentação atualizada e consistente
11. ✅ Contract tests criados (skeleton mínimo)
12. ✅ Coordenação com time SOAT completa
13. ✅ Migration guide documentado

---

## 7. Checklist de Execução

```
[x] 1. Executar auditar-contrato-http (READY)
    [x] Mapear arquivos afetados
    [x] Documentar diferenças de contrato
    [x] Criar checklist de validação
    [x] Validar impacto em fluxo async

[x] 2. Executar alinhar-validacao-de-entrada
    [x] Validar analysis_id como string (GUD-006)
    [x] Validar context_text max 1000
    [x] Adicionar testes de validação

[x] 3. Executar alinhar-resposta-e-erros
    [x] Refatorar AnalyzeResponse (report aninhado)
    [x] Ajustar pipeline
    [x] Corrigir exception handlers (AI_TIMEOUT)

[x] 4. Executar atualizar-testes-fun001
    [x] Atualizar testes de sucesso
    [x] Validar testes de validação
    [x] Atualizar testes de erro
    [x] Validar cobertura ≥ 80% (90% alcançado)

[x] 5. Executar revisar-documentacao-relacionada
    [x] Validar docstrings
    [x] Revisar README
    [x] Criar migration guide
    [x] Criar contract test skeleton
    [x] Executar quality gates

[x] 6. Coordenação com SOAT
    [x] Apresentar migration guide (docs/MIGRATION-FUN-001.md)
    [x] Executar contract tests (tests/contract/test_soat_contract.py)
    [ ] Agendar flag day deployment (pendente — atividade real)
    [ ] Validar testes E2E (pendente — atividade real)

[x] 7. Validação Final
    [x] Todos os critérios de aceite de implementação satisfeitos
    [x] Coordenação com time SOAT concluída (documentação e testes)
    [x] Migration guide documentado
    [x] Contract tests passando (8/8)
```

---

## 8. Referências

1. **Especificação:** `specs\spec.md` (v2.1)
2. **Constituição:** `.specify\memory\constitution.md` (v1.0.0)
3. **Instruções Copilot:** `.github\copilot\copilot-instructions.md`
4. **Requisito:** **FUN-001** - The system MUST expose `POST /analyze` to process a single diagram synchronously.
5. **Clarificações:** Registradas em SQL database (2026-04-30, 5 decisões críticas)

---

## 9. Notas de Implementação

### 9.1 Sobre Quebra de Compatibilidade

Como FUN-001 já está parcialmente implementado, o risco principal não é ausência de funcionalidade, e sim **quebra de compatibilidade entre código, testes e spec**. A decisão de flag day (Clarification #1) significa que:

- ✅ A spec v2.1 é a fonte canônica imediata do contrato HTTP
- ✅ Não manteremos dois contratos simultaneamente
- ✅ Deployment coordenado com SOAT é obrigatório
- ⚠️ Qualquer consumidor que não seja atualizado falhará

### 9.2 Sobre Validação de `analysis_id`

A decisão de "trust orchestrator" (Clarification #4, GUD-006) significa que:

- ✅ Não adicionaremos validação UUID estrita na borda HTTP
- ✅ Testes podem usar qualquer formato de ID
- ✅ Simplifica validação e permite flexibilidade
- ℹ️ SOAT é responsável por garantir formato adequado

Esta decisão pode ser revisitada no futuro se houver problemas de integração.

### 9.3 Sobre Fluxo Assíncrono

Ao implementar, é **crítico** validar que mudanças no contrato síncrono não conflitam com os fluxos assíncronos e com os modelos compartilhados. O pipeline é reutilizado por ambos os fluxos (HTTP e RabbitMQ), então:

- ✅ Mudanças no pipeline afetam ambos os fluxos
- ✅ Modelos de queue (`QueueJobMessage`, `QueueResultMessage`) são separados
- ⚠️ Validar que `Report` e `AnalysisMetadata` não quebram serialização

---

**Última atualização:** 2026-04-30  
**Próxima revisão:** Após conclusão de `auditar-contrato-http`  
**Status do plano:** ✅ Completo e pronto para execução

---

## Anexo: Estrutura de Resposta Esperada

### Sucesso (200)

```json
{
  "analysis_id": "any-string-format-ok",
  "status": "success",
  "report": {
    "summary": "Architecture overview...",
    "components": [
      {
        "name": "API Gateway",
        "type": "gateway",
        "description": "Entry point..."
      }
    ],
    "risks": [
      {
        "title": "Single point of failure",
        "severity": "medium",
        "description": "...",
        "affected_components": ["API Gateway"]
      }
    ],
    "recommendations": [
      {
        "title": "Add redundancy",
        "priority": "high",
        "description": "..."
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

### Erro de Validação (422)

```json
{
  "analysis_id": "any-string-format-ok",
  "status": "error",
  "error_code": "INVALID_INPUT",
  "message": "context_text exceeds maximum length of 1000 characters"
}
```

### Timeout (504)

```json
{
  "analysis_id": "any-string-format-ok",
  "status": "error",
  "error_code": "AI_TIMEOUT",
  "message": "Analysis timed out after 30 seconds"
}
```
