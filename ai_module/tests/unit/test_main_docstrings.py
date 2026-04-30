from __future__ import annotations

import inspect

from ai_module import main as main_module

EXPECTED_DOCSTRINGS = {
    "__module__": "Ponto de entrada da aplicação FastAPI.",
    "lifespan": "Gerencia o ciclo de vida de inicialização e encerramento da aplicação.",
    "_get_analysis_id": (
        "Obtém o identificador da análise a partir do estado da requisição ou dos cabeçalhos."
    ),
    "security_headers": "Adiciona cabeçalhos de segurança a todas as respostas HTTP.",
    "unsupported_format_handler": (
        "Retorna a resposta HTTP para erros de formato de arquivo não suportado."
    ),
    "invalid_input_handler": "Retorna a resposta HTTP para erros de entrada inválida.",
    "ai_failure_handler": "Retorna a resposta HTTP para falhas internas na análise por IA.",
    "timeout_handler": "Retorna a resposta HTTP para erros de tempo limite na análise por IA.",
    "generic_exception_handler": "Retorna a resposta HTTP para exceções não tratadas.",
    "dev": "Inicia o servidor em modo de desenvolvimento com recarga automática.",
    "main": "Inicia o servidor em modo de produção.",
}


def test_main_module_docstrings_are_standardized_in_portuguese() -> None:
    assert inspect.getdoc(main_module) == EXPECTED_DOCSTRINGS["__module__"]

    for name, expected_docstring in EXPECTED_DOCSTRINGS.items():
        if name == "__module__":
            continue

        assert inspect.getdoc(getattr(main_module, name)) == expected_docstring
