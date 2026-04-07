# FIAP Hackathon Fase 5

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135.3-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)

Repositório do projeto da FIAP Hackathon Fase 5, com foco em análise automatizada de diagramas de arquitetura usando IA.

O núcleo atual é o módulo [ai_module](ai_module), responsável por receber diagramas (imagem ou PDF), executar um pipeline multimodal com LLM e retornar um relatório técnico estruturado em JSON.

> [!IMPORTANT]
> Este serviço de IA não faz persistência de dados, autenticação nem orquestração de fluxo de negócio. Essas responsabilidades ficam em outros componentes da solução.

## Visão Geral

- Entrada via API REST: upload de diagrama + `analysis_id` para rastreabilidade.
- Pré-processamento de arquivo: validação de tipo real, tamanho e conversão de PDF para imagem.
- Análise com provedor LLM configurável (`gemini` ou `openai`).
- Validação de saída com schema rígido usando Pydantic.
- Resposta padronizada contendo resumo, componentes, riscos e recomendações.

## Estrutura do Repositório

```text
.
├── ai_module/          # Serviço principal de IA (FastAPI)
├── docs/               # Documentação complementar
├── infra/              # Artefatos de containerização e compose
├── specs/              # Especificações e plano de implementação
└── README.md
```

## Escopo Funcional do Módulo de IA

- Recebe arquivos `.png`, `.jpg`, `.jpeg` e `.pdf`.
- Processa a primeira página de PDF.
- Aplica guardrails de entrada e saída.
- Entrega relatório estruturado no formato esperado pelo orquestrador.
- Expõe endpoints de health e métricas para operação.

## API Principal

### `POST /analyze`

`multipart/form-data` com:

- `file` (obrigatório)
- `analysis_id` (obrigatório, UUID)

Resposta de sucesso:

- `analysis_id`
- `status`
- `report` (summary, components, risks, recommendations)
- `metadata` (modelo, tempo de processamento e tipo de entrada)

### `GET /health`

- `200` quando saudável
- `503` em modo degradado (por exemplo, chave de API ausente)

### `GET /metrics`

Retorna métricas em formato Prometheus.

## Execução Rápida

### 1. Ambiente local (sem Docker)

Pré-requisitos:

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

Comandos:

```bash
cd ai_module
uv sync
uv run uvicorn ai_module.main:app --host 0.0.0.0 --port 8000 --reload
```

Acesse:

- `http://localhost:8000/docs`
- `http://localhost:8000/health`
- `http://localhost:8000/metrics`

### 2. Execução com Docker Compose

Na raiz do repositório:

```bash
docker compose -f infra/compose.yaml up --build
```

> [!NOTE]
> Crie o arquivo `ai_module/.env` com as variáveis necessárias antes de subir o serviço.

## Configuração Essencial

As variáveis mais importantes do módulo estão em [ai_module/.env-exemplo](ai_module/.env-exemplo):

- `LLM_PROVIDER` (`gemini` ou `openai`)
- `LLM_MODEL`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `MAX_FILE_SIZE_MB`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_RETRIES`
- `LOG_LEVEL`

## Qualidade e Testes

Dentro de [ai_module](ai_module):

```bash
uv run pytest
uv run pytest --cov --cov-report=term-missing
uv run ruff check .
uv run mypy src
```

