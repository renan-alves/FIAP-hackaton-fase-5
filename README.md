# FIAP Hackathon Fase 5

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135.3-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)

Repositório do projeto da FIAP Hackathon Fase 5, com foco em análise automatizada de diagramas de arquitetura por IA.

O módulo principal é [ai_module](ai_module), um microserviço FastAPI que recebe diagramas (imagem ou PDF), executa um pipeline multimodal com LLM e retorna um relatório técnico estruturado em JSON.

> [!IMPORTANT]
> Este serviço não é responsável por persistência de dados, autenticação ou orquestração de negócio.

## Project Name and Description

- Nome do projeto: FIAP Hackathon Fase 5
- Propósito principal: análise técnica automatizada de diagramas de arquitetura usando IA
- Escopo funcional: validação de entrada, pré-processamento de arquivos, análise por LLM, validação estrita de saída e resposta estruturada para integração com orquestrador

## Technology Stack

Versões consolidadas a partir de [ai_module/pyproject.toml](ai_module/pyproject.toml) e [.github/copilot/copilot-instructions.md](.github/copilot/copilot-instructions.md):

- Python: >=3.11,<3.14
- FastAPI: 0.135.3
- Pydantic: 2.12.5
- pydantic-settings: 2.13.1
- Uvicorn: 0.44.0
- OpenAI SDK: 2.30.0
- Google GenAI SDK: >=1.0.0,<2.0.0
- Pillow: 12.2.0
- PyMuPDF: 1.27.2.2
- python-json-logger: 4.1.0
- python-multipart: 0.0.24
- httpx: 0.28.1
- Qualidade: Ruff 0.15.9, MyPy 1.20.0
- Testes: pytest 9.0.2, pytest-asyncio 1.3.0, pytest-cov 7.1.0
- Infra local: Docker e Docker Compose

## Project Architecture

O módulo de IA segue um estilo de microserviço com separação em camadas:

- API: entrada HTTP, composição de rotas e contrato de resposta
- Core: regras de negócio, pipeline, validações, métricas, configuração e logging
- Adapters: integração com provedores LLM via contrato comum
- Models: schemas Pydantic para requests, responses e enums

Fluxo de alto nível:

```text
Cliente -> /analyze (API)
	-> preprocessamento e validações (core)
	-> prompt + chamada LLM (adapters)
	-> validação/normalização de resposta (core/models)
	-> resposta JSON estruturada
```

Referência de arquitetura e padrões: [.github/copilot/copilot-instructions.md](.github/copilot/copilot-instructions.md)

## Getting Started

### Pré-requisitos

- Python 3.11+
- uv
- Docker e Docker Compose (opcional)

### Execução local

```bash
cd ai_module
uv sync
uv run uvicorn ai_module.main:app --host 0.0.0.0 --port 8000 --reload
```

### Execução com Docker Compose

```bash
docker compose -f infra/compose.yaml up --build
```

### Configuração

Crie o arquivo ai_module/.env a partir de [ai_module/.env-exemplo](ai_module/.env-exemplo) e configure, no mínimo:

- LLM_PROVIDER (gemini ou openai)
- LLM_MODEL
- GEMINI_API_KEY
- OPENAI_API_KEY
- MAX_FILE_SIZE_MB
- LLM_TIMEOUT_SECONDS
- LLM_MAX_RETRIES
- LOG_LEVEL

### Endpoints principais

- POST /analyze
- GET /health
- GET /metrics

## Project Structure

```text
.
├── ai_module/                # Serviço principal de IA (FastAPI)
│   ├── src/ai_module/api/    # Rotas e camada HTTP
│   ├── src/ai_module/core/   # Pipeline, validação, settings, métricas, logger
│   ├── src/ai_module/adapters/ # Integrações Gemini/OpenAI
│   ├── src/ai_module/models/ # Schemas Pydantic
│   └── tests/                # Unit e integration tests
├── docs/                     # Especificações e documentação complementar
├── infra/                    # Dockerfile e compose
└── README.md
```

## Key Features

- Suporte a PNG, JPG, JPEG e PDF
- Conversão das primeiras 3 páginas de PDF para imagens normalizadas
- Pipeline com provedor LLM configurável (Gemini/OpenAI)
- Validação de saída contra schema rígido
- Guardrails de entrada e saída
- Observabilidade com logs estruturados e métricas Prometheus
- Health check com sinalização de modo degradado

## Development Workflow

Fluxo recomendado para desenvolvimento local:

1. Sincronizar dependências com uv
2. Executar serviço em modo reload
3. Implementar mudanças preservando os limites de camada (api/core/adapters/models)
4. Rodar lint, tipagem e testes antes de merge

Comandos úteis em [ai_module](ai_module):

```bash
uv run ruff check .
uv run mypy src
uv run pytest
uv run pytest --cov --cov-report=term-missing
```

Observação: não há estratégia de branching formal documentada neste repositório.

## Coding Standards

Padrões principais de código, consolidados de [.github/copilot/copilot-instructions.md](.github/copilot/copilot-instructions.md):

- Compatibilidade estrita com Python 3.11+
- Uso consistente de type hints
- Uso de APIs Pydantic v2
- Lógica de negócio fora das rotas
- Exceções de domínio mapeadas centralmente para HTTP
- Logging estruturado com campos event e details
- Consistência com padrões existentes acima de recomendações externas

## Testing

Estratégia atual:

- Framework: pytest
- Assíncrono: pytest-asyncio
- Cobertura: pytest-cov
- Organização: testes unitários e de integração em ai_module/tests
- Fixtures compartilhadas em tests/conftest.py

Comandos:

```bash
cd ai_module
uv run pytest
uv run pytest --cov --cov-report=term-missing
```

## License

Não há arquivo de licença explícito no repositório até o momento.

