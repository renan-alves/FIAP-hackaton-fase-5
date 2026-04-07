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

| Variavel | Default | Descricao |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | Provedor (`gemini` ou `openai`) |
| `LLM_MODEL` | `gemini-1.5-pro` | Modelo utilizado no provedor |
| `GEMINI_API_KEY` | vazio | Obrigatoria quando `LLM_PROVIDER=gemini` |
| `OPENAI_API_KEY` | vazio | Obrigatoria quando `LLM_PROVIDER=openai` |
| `MAX_FILE_SIZE_MB` | `10` | Tamanho maximo do arquivo de entrada |
| `LLM_TIMEOUT_SECONDS` | `60` | Timeout da chamada ao LLM |
| `LLM_MAX_RETRIES` | `2` | Numero maximo de tentativas |
| `LOG_LEVEL` | `INFO` | Nivel de log |
| `APP_HOST` | `0.0.0.0` | Host de bind da aplicacao |
| `APP_PORT` | `8000` | Porta HTTP |
| `APP_ENV` | `dev` | Ambiente de execucao |

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

2. Instale dependencias:

```bash
uv sync
```

3. Confirme seu `.env` (principalmente `LLM_PROVIDER` e API key).

4. Rode em modo desenvolvimento com hot reload:

```bash
uv run uvicorn ai_module.main:app --host 0.0.0.0 --port 8000 --reload
```

5. Acesse:

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics

## Tutorial - rodando com docker

Execute os comandos a partir da raiz do repositorio.

1. Garanta que o arquivo `ai_module/.env` exista.

2. Suba com Docker Compose:

```bash
docker compose -f infra/compose.yaml up --build
```

3. Acesse:

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics

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

Exemplo com `curl`:

```bash
curl -X POST "http://localhost:8000/analyze" \
  -F "analysis_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "file=@./sample-architecture.png"
```

Codigos de erro principais:

| Codigo | HTTP | Causa |
|---|---|---|
| `INVALID_INPUT` | 422 | Arquivo vazio, corrompido ou acima do limite |
| `UNSUPPORTED_FORMAT` | 422 | Formato diferente de PNG/JPEG/PDF |
| `AI_FAILURE` | 500 | Falha no pipeline de IA apos retries |

### GET /health

- `200`: servico saudavel
- `503`: modo degradado (exemplo: API key ausente)

### GET /metrics

Retorna contadores em formato Prometheus.

## Observabilidade e seguranca

Metricas expostas em `/metrics`:

- `ai_module_requests_success_total`
- `ai_module_requests_error_total`
- `ai_module_processing_time_ms_total`
- `ai_module_llm_retries_total`

Headers de seguranca adicionados nas respostas HTTP:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`

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
