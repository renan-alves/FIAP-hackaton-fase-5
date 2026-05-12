# AI Module - Architecture Diagram Analyser

[![Python](https://img.shields.io/badge/Python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![uv](https://img.shields.io/badge/uv-package%20manager-de5d43?style=flat-square)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/badge/linter-ruff-red?style=flat-square)](https://github.com/astral-sh/ruff)

Microservico de analise de diagramas de arquitetura com IA.
Recebe imagens ou PDF e devolve um relatorio tecnico estruturado.

Este modulo faz parte do projeto FIAP Hackathon Fase 5 e cuida apenas do pipeline de IA.

## O que este servico entrega

- Entrada de arquivos PNG, JPEG e PDF (somente a primeira pagina)
- Suporte a dois provedores LLM: Gemini e OpenAI
- Saida validada em JSON com resumo, componentes, riscos e recomendacoes
- Endpoint de saude e endpoint de metricas em formato Prometheus
- Inicializacao resiliente: se faltar API key, o servico sobe em modo degradado (sem crash)

## Sumario

- [Requisitos](#requisitos)
- [Configuracao](#configuracao)
- [Tutorial - rodando localmente](#tutorial---rodando-localmente)
- [Tutorial - rodando com docker](#tutorial---rodando-com-docker)
- [Uso rapido da API](#uso-rapido-da-api)
- [Observabilidade e seguranca](#observabilidade-e-seguranca)
- [Worker RabbitMQ](#worker-rabbitmq)
- [Desenvolvimento](#desenvolvimento)

## Requisitos

- Python 3.11+
- uv
- Docker e Docker Compose (opcional)

Instalar uv:

```bash
pip install uv
```

## Configuracao

Crie um arquivo `.env` dentro da pasta `ai_module/`.

| Variavel              | Default          | Descricao                                |
|-----------------------|------------------|------------------------------------------|
| `LLM_PROVIDER`        | `gemini`         | Provedor (`gemini` ou `openai`)          |
| `LLM_MODEL`           | `gemini-1.5-pro` | Modelo utilizado no provedor             |
| `GEMINI_API_KEY`      | vazio            | Obrigatoria quando `LLM_PROVIDER=gemini` |
| `OPENAI_API_KEY`      | vazio            | Obrigatoria quando `LLM_PROVIDER=openai` |
| `MAX_FILE_SIZE_MB`    | `10`             | Tamanho maximo do arquivo de entrada     |
| `LLM_TIMEOUT_SECONDS` | `60`             | Timeout da chamada ao LLM                |
| `LLM_MAX_RETRIES`     | `2`              | Numero maximo de tentativas              |
| `LOG_LEVEL`           | `INFO`           | Nivel de log                             |
| `APP_HOST`            | `0.0.0.0`        | Host de bind da aplicacao                |
| `APP_PORT`            | `8000`           | Porta HTTP                               |
| `APP_ENV`             | `dev`            | Ambiente de execucao                     |
| `RABBITMQ_URL`        | *(vazio)*        | URL de conexao ao broker RabbitMQ        |
| `RABBITMQ_EXCHANGE`   | `analysis`       | Exchange DIRECT para requests/results    |
| `RABBITMQ_INPUT_QUEUE` | `analysis.requests` | Fila de entrada de requisicoes          |
| `RABBITMQ_OUTPUT_QUEUE` | `analysis.results` | Fila de saida de resultados             |
| `RABBITMQ_WORKER_ENABLED` | `false`      | Habilita o consumer RabbitMQ no startup  |

Exemplo de `.env`:

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-pro
GEMINI_API_KEY=your-key-here
LOG_LEVEL=INFO
APP_PORT=8000
```

> [!NOTE]
> Se a API key do provedor selecionado estiver ausente, a aplicacao sobe em modo degradado e retorna `503` no endpoint `/health`.

## Tutorial - rodando localmente

1. Entre na pasta do modulo:

```bash
cd ai_module
```

1. Instale dependencias:

```bash
uv sync
```

1. Confirme seu `.env` (principalmente `LLM_PROVIDER` e API key).

2. Rode em modo desenvolvimento com hot reload:

```bash
uv run uvicorn ai_module.main:app --host 0.0.0.0 --port 8000 --reload
```

1. Acesse:

- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>
- Metrics: <http://localhost:8000/metrics>

## Tutorial - rodando com docker

Execute os comandos a partir da raiz do repositorio.

1. Garanta que o arquivo `ai_module/.env` exista.

2. Suba com Docker Compose:

```bash
docker compose -f infra/compose.yaml up --build
```

1. Acesse:

- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>
- Metrics: <http://localhost:8000/metrics>

Opcional: build e execucao manuais sem compose.

```bash
docker build -f infra/Dockerfile -t ai-module:latest .
docker run --rm --env-file ai_module/.env -p 8000:8000 ai-module:latest
```

## Uso rapido da API

### POST /analyze

Request: `multipart/form-data`

- `file`: arquivo `.png`, `.jpg`, `.jpeg` ou `.pdf`
- `analysis_id`: UUID de correlacao
- `context_text` (opcional): texto auxiliar com limite de 1000 caracteres

Regra de validacao:

- Se `context_text` exceder 1000 caracteres, a API retorna `422 Unprocessable Entity` automaticamente.

Exemplo com `curl`:

```bash
curl -X POST "http://localhost:8000/analyze" \
  -F "analysis_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "context_text=Fluxo principal passando por API e fila" \
  -F "file=@./sample-architecture.png"
```

Metadados da resposta:

- `metadata.context_text_provided`: indica se `context_text` foi enviado
- `metadata.context_text_length`: tamanho do texto enviado
- `metadata.conflict_detected`: indica conflito entre contexto textual e evidencia visual
- `metadata.conflict_decision`: decisao aplicada (`NO_CONFLICT` ou `DIAGRAM_FIRST`)
- `metadata.conflict_policy`: politica ativa (`DIAGRAM_FIRST`)

Importante:

- O contexto textual e tratado apenas como dado auxiliar no prompt.
- Em caso de conflito entre `context_text` e diagrama, prevalece o diagrama (`DIAGRAM_FIRST`).

Codigos de erro principais:

| Codigo               | HTTP | Causa                                        |
|----------------------|------|----------------------------------------------|
| `INVALID_INPUT`      | 422  | Arquivo vazio, corrompido ou acima do limite |
| `UNSUPPORTED_FORMAT` | 422  | Formato diferente de PNG/JPEG/PDF            |
| `AI_TIMEOUT`         | 500  | Timeout no provedor LLM apos retries         |
| `AI_FAILURE`         | 500  | Falha no pipeline de IA apos retries         |
| `INTERNAL_ERROR`     | 500  | Erro interno nao classificado                |

### GET /health

- `200`: servico saudavel
- `503`: modo degradado (exemplo: API key ausente)

> [!IMPORTANT]
> Limitacao conhecida (MVP): o estado de saude eh mantido em memoria no processo (`_service_healthy`).
> Em execucao com multiplos workers (ex.: Gunicorn/Uvicorn workers), cada worker possui seu proprio estado.
> Isso pode gerar respostas divergentes entre workers para `/health`.

### GET /metrics

Retorna contadores em formato Prometheus.

## Observabilidade e seguranca

Metricas expostas em `/metrics`:

- `ai_requests_total{status="success|error"}` — requisicoes HTTP ao endpoint `/analyze`
- `ai_processing_time_ms_avg` — tempo medio de processamento em ms
- `ai_llm_retries_total` — total de retries do LLM
- `ai_llm_provider_active{provider="..."}` — provedor ativo (sempre 1)
- `queue_messages_consumed_total` — mensagens consumidas da fila de entrada
- `queue_messages_published_total` — total de mensagens publicadas (sucesso + erro)
- `queue_results_published_total{status="success|error"}` — resultados publicados por status
- `queue_publish_failures_total` — falhas apos todas as tentativas de publicacao
- `queue_validation_errors_total` — erros de validacao de schema nas mensagens consumidas
- `queue_pipeline_errors_total` — erros no pipeline de analise de IA

Headers de seguranca adicionados nas respostas HTTP:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`

## Worker RabbitMQ

O servico suporta consumo assincrono de mensagens via RabbitMQ, habilitado pela variavel `RABBITMQ_WORKER_ENABLED=true`.

### Como funciona

1. O `main.py` inicia o `WorkerLifecycle` junto com o FastAPI (evento `startup`).
2. O `Consumer` se conecta ao broker, declara o exchange DIRECT `analysis`, declara a fila `analysis.requests`, faz bind da fila no exchange e registra o callback.
3. Para cada mensagem recebida:
   - Decodifica JSON → valida schema (`QueueAnalysisRequest`)
   - Decodifica base64 dos bytes do arquivo
   - Executa o pipeline de IA (`run_pipeline`)
   - Publica o resultado em `analysis.results` via `Publisher`
4. Mensagens malformadas (JSON invalido ou schema invalido) sao descartadas sem requeue (NACK).
5. Erros de pipeline publicam uma resposta de erro na fila de saida e fazem ACK.

### Formatos de mensagem

#### Requisicao (`analysis.requests`)

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_bytes_b64": "<base64 do arquivo>",
  "file_name": "diagram.png",
  "context_text": "Opcional: texto auxiliar"
}
```

#### Resposta de sucesso (`analysis.results`)

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "report": { "..." },
  "metadata": { "..." }
}
```

#### Resposta de erro (`analysis.results`)

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "error",
  "error_code": "INTERNAL_ERROR",
  "message": "Descricao do erro"
}
```

Codigos de erro possiveis:

| `error_code`         | Causa                                                  |
|----------------------|--------------------------------------------------------|
| `INVALID_INPUT`      | Input invalido rejeitado pelo pipeline                 |
| `UNSUPPORTED_FORMAT` | Formato de arquivo nao suportado                       |
| `AI_TIMEOUT`         | Timeout no LLM ou no pipeline de IA                    |
| `AI_FAILURE`         | Falha na chamada ao servico de IA                      |
| `INTERNAL_ERROR`     | Erro nao classificado durante o pipeline               |

Os contratos de mensagem estao definidos em:

- `specs/FUN-010-contracts/success-result.json`
- `specs/FUN-010-contracts/error-result.json`

### Habilitando o worker

Adicione ao `.env`:

```env
RABBITMQ_WORKER_ENABLED=true
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
RABBITMQ_EXCHANGE=analysis
RABBITMQ_INPUT_QUEUE=analysis.requests
RABBITMQ_OUTPUT_QUEUE=analysis.results
```

### Publicacao de resultados (Publisher)

O `Publisher` tenta publicar o resultado ate 3 vezes com backoff exponencial (`2^tentativa` segundos entre tentativas). Se todas as tentativas falharem, a excecao `PublishError` e propagada e registrada com campos estruturados:

| Campo              | Descricao                                          |
|--------------------|----------------------------------------------------|
| `analysis_id`      | Identificador da analise                           |
| `event`            | `publish_failed` quando todas as tentativas esgotam |
| `error_type`       | Tipo da excecao Python                             |
| `retry_count`      | Numero de tentativas realizadas (sempre 3)         |
| `queue_name`       | Nome da fila de saida configurada                  |
| `connection_state` | `connected` ou `disconnected` no momento da falha |

A metrica `queue_publish_failures_total` e incrementada a cada evento de falha total.
A metrica `queue_results_published_total{status="success|error"}` contabiliza separadamente publicacoes bem-sucedidas de respostas de sucesso e de erro.

### Resolucao de problemas

| Sintoma                              | Causa provavel                        | Solucao                                      |
|--------------------------------------|---------------------------------------|----------------------------------------------|
| Worker nao inicia                    | `RABBITMQ_WORKER_ENABLED=false`       | Defina a variavel como `true`                |
| Conexao recusada                     | RabbitMQ nao esta rodando             | Suba o broker com `docker compose up rabbit` |
| Mensagens na DLQ                     | JSON invalido ou schema errado        | Valide o payload do publicador               |
| Respostas de erro com `AI_TIMEOUT`   | LLM demorando mais que o timeout      | Aumente `LLM_TIMEOUT_SECONDS`                |
| Worker nao publica resultados        | Fila de saida nao declarada           | Verifique `RABBITMQ_OUTPUT_QUEUE`            |

## Desenvolvimento

Rodar testes:

```bash
cd ai_module
uv run pytest
```

Cobertura:

```bash
uv run pytest --cov --cov-report=term-missing
```

Lint e type-check:

```bash
uv run ruff check .
uv run mypy src
```

Formatacao:

```bash
uv run ruff format .
```

## Limitações Conhecidas

| Limitação                                                    | Impacto                                        | Mitigação                                                                          |
|--------------------------------------------------------------|------------------------------------------------|------------------------------------------------------------------------------------|
| LLMs podem alucinar componentes não visíveis                 | Relatório impreciso                            | Guardrail de saída + instrução explícita no prompt                                 |
| `context_text` pode conflitar com o diagrama                 | Ambiguidade de interpretação                   | Guardrail de conflito + política `DIAGRAM_FIRST` com decisão explícita no metadata |
| Diagramas com baixa resolução reduzem precisão               | Componentes não identificados                  | Documentado no `metadata` da resposta                                              |
| PDFs com múltiplas páginas: apenas primeira página analisada | Análise incompleta                             | Documentado no README como limitação do MVP                                        |
| Respostas do LLM não são determinísticas                     | Variação entre execuções                       | Documentado como comportamento esperado                                            |
| Custo por chamada ao LLM                                     | Custo operacional em escala                    | Monitorar via métricas; fora do escopo do MVP                                      |
| Sem autenticação própria                                     | Acesso irrestrito ao endpoint                  | Autenticação delegada ao API Gateway (SOAT); serviço restrito à rede interna       |
| Dependência de provedor externo                              | Indisponibilidade do Gemini/OpenAI causa falha | Timeout configurável + `AI_FAILURE` claro; troca de provider via env var           |
| Imagens enviadas ao LLM externo                              | Dados do diagrama saem do ambiente local       | Deve ser informado ao usuário final pelo sistema                                   |
