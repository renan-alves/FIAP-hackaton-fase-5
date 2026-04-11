"""Pipeline de análise de IA orquestrando pré-processamento, chamadas ao LLM e validação."""

from __future__ import annotations

# Nota 1: A PEP 563 (Python 3.7+) muda a avaliação de anotações para o modo "adiado".
#   As anotações são armazenadas como strings no momento da definição e só são avaliadas
#   quando explicitamente solicitadas (ex.: via typing.get_type_hints()). Isso permite
#   referências futuras (usar um tipo antes de declará-lo) sem precisar usar aspas manualmente.
import time

# Nota 2: O módulo 'time' fornece time.monotonic(), que retorna um float representando
#   segundos desde um ponto de referência arbitrário. Ao contrário de time.time(), o
#   relógio monotônico nunca retrocede — é imune a ajustes de relógio do sistema
#   (ex.: correções NTP) — tornando-o a escolha correta para medir durações
#   dentro de um único processo.
from ai_module.adapters.base import LLMAdapter
from ai_module.core.exceptions import (
    AIFailureError,
    InvalidInputError,
    LLMCallError,
    LLMTimeoutError,
    UnsupportedFormatError,
)
from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics
from ai_module.core.preprocessor import preprocess
from ai_module.core.prompt_builder import (
    build_correction_prompt,
    build_system_prompt,
    build_user_prompt,
)
from ai_module.core.report_validator import validate_and_normalize
from ai_module.core.settings import settings
from ai_module.models.report import AnalyzeResponse, Report, ReportMetadata

logger = get_logger(__name__, level=settings.LOG_LEVEL)
# Nota 3: Padrão de logger em nível de módulo. __name__ resolve para o caminho completo
#   com pontos (ex.: 'ai_module.core.pipeline'), então cada registro de log identifica
#   automaticamente seu módulo de origem na saída estruturada. Passar level=settings.LOG_LEVEL
#   permite ajustar a verbosidade em tempo de execução via variável de ambiente.

_PROVIDER = settings.LLM_PROVIDER.upper()
# Nota 4: _PROVIDER é avaliado uma vez no momento da importação do módulo, não a cada
#   requisição. O underscore inicial indica escopo privado do módulo por convenção.
#   .upper() normaliza o valor para que as comparações de provedor sejam insensíveis
#   a maiúsculas/minúsculas, independente de como a variável de ambiente foi definida
#   (ex.: "gemini" ou "GEMINI").


# ── Auxiliares ───────────────────────────────────────────────────────────────

def _truncate_for_log(value: str, limit: int = 500) -> str:
    """Compacta e trunca uma string para inclusão segura em entradas de log estruturado.

    Substitui quebras de linha por sequências de escape literais e corta em ``limit``
    caracteres, adicionando reticências quando o valor é maior.

    Parameters
    ----------
    value : str
        String bruta a compactar.
    limit : int
        Tamanho máximo em caracteres antes do truncamento (padrão 500).

    Returns
    -------
    str
        String de uma linha com no máximo ``limit + 3`` caracteres.
    """ 
    # Nota 5: O truncamento de log protege contra entradas ilimitadas. Respostas brutas
    #   do LLM podem conter milhares de caracteres; registrá-las literalmente em um
    #   agregador de logs (ex.: CloudWatch, Datadog) desperdiça cota de armazenamento e
    #   retarda a busca de texto. Substituir quebras de linha literais ('\n') pelas
    #   sequências de escape ('\\n') garante que cada evento ocupe exatamente uma linha
    #   no fluxo de saída, requisito para parsers JSON como Fluentd ou Logstash.
    compact = value.replace("\n", "\\n").replace("\r", "\\r")
    return compact[:limit] + "..." if len(compact) > limit else compact


def _file_signature_hex(file_bytes: bytes, limit: int = 16) -> str:
    """Return the first ``limit`` bytes of a file as a hex string.

    Useful for diagnostic logging — allows identification of file
    type by magic bytes without exposing the full content.

    Parameters
    ----------
    file_bytes : bytes
        Raw file content.
    limit : int
        Number of leading bytes to include (default 16).

    Returns
    -------
    str
        Hex-encoded prefix (e.g. ``"89504e47..."``).
    """
    return file_bytes[:limit].hex()


def _classify_validation_error(error: str) -> str:
    """Mapeia uma mensagem de erro de validação para uma instrução de correção direcionada.

    Parameters
    ----------
    error : str
        String de erro de validação retornada por ``validate_and_normalize``.

    Returns
    -------
    str
        Instrução de correção legível para incorporar no próximo prompt do LLM,
        permitindo que o modelo corrija o problema específico.
    """
    # Nota 7: Padrão de classificador/roteador de erros. Cada ramo mapeia uma palavra-chave
    #   encontrada na string de erro de validação para uma instrução de reparo direcionada.
    #   Fornecer instruções específicas (ex.: "o campo components está ausente") melhora
    #   drasticamente o sucesso da correção pelo LLM em comparação a prompts genéricos
    #   como "corrija isso". Verificações de pertencimento de substring ('in') são usadas
    #   em vez de regex por velocidade e legibilidade — as strings de erro seguem padrões fixos.
    if "JSON_PARSE_ERROR" in error:
        return (
            "Your response was not valid JSON. "
            "Return ONLY the raw JSON object, no markdown, no extra text."
        )
    if "components" in error:
        return (
            "The 'components' field is missing or empty. "
            "You MUST identify at least one component visible in the diagram."
        )
    if "summary" in error:
        return (
            "The 'summary' field is missing or exceeds 500 characters. "
            "Provide a concise summary of at most 500 characters."
        )
    if "severity" in error:
        return "Use only 'high', 'medium', or 'low' for risk severity."
    if "priority" in error:
        return "Use only 'high', 'medium', or 'low' for recommendation priority."
    if "SCHEMA_ERROR" in error:
        return (
            f"Schema validation failed: {error}. "
            "Fix only the invalid fields and return the complete JSON."
        )
    return f"Fix the invalid response. Error: {error}"


# ── Guarda de consistência semântica ─────────────────────────────────────────

def _apply_semantic_guardrails(report: Report, analysis_id: str) -> Report:
    """Valida e corrige a consistência entre seções do relatório.

    Regras aplicadas:

    1. ``Risk.affected_components`` deve referenciar apenas nomes de componentes
       conhecidos. Referências desconhecidas são removidas silenciosamente (guarda
       contra alucinações do LLM).
    2. O summary deve mencionar ao menos um componente identificado. Caso não mencione,
       um ``WARNING`` é registrado, mas o relatório não é rejeitado, pois o LLM pode
       usar sinônimos ou abreviações.

    Parameters
    ----------
    report : Report
        Relatório validado a inspecionar e corrigir in-place.
    analysis_id : str
        Identificador de correlação para os logs estruturados.

    Returns
    -------
    Report
        O mesmo objeto de relatório com referências alucinadas de componentes removidas.
    """
    # Nota 8: A compreensão de conjunto constrói um conjunto de busca com todos os nomes
    #   de componentes conhecidos em tempo O(n). Testes de pertencimento subsequentes
    #   ('in component_names') são O(1) em média, contra O(n) para uma lista. Isso importa
    #   quando o relatório tem muitos riscos, cada um referenciando múltiplos componentes —
    #   a diferença de conjuntos abaixo executa uma vez por risco e se beneficia muito
    #   da busca rápida em conjunto.
    component_names = {c.name for c in report.components}

    for risk in report.risks:
        # Nota 9: Diferença de conjuntos (A - B) retorna elementos presentes em A mas
        #   ausentes em B — aqui, nomes de componentes que o LLM mencionou num risco mas
        #   que não existem na lista de componentes validados. Isso detecta alucinações:
        #   LLMs às vezes inventam nomes de entidades plausíveis que nunca foram
        #   identificadas no diagrama, criando referências cruzadas inválidas.
        unknown_refs = set(risk.affected_components) - component_names
        if unknown_refs:
            logger.warning(
                "Risk references unknown components — removing hallucinated refs",
                extra={
                    "event": "semantic_guardrail_component_ref",
                    "analysis_id": analysis_id,
                    "details": {
                        "risk_title": risk.title,
                        "unknown_refs": list(unknown_refs),
                        "known_components": list(component_names),
                    },
                },
            )
            risk.affected_components = [
                c for c in risk.affected_components if c in component_names
            ]

    # Nota 10: Padrão de "guarda suave" — registra um aviso mas não modifica nem rejeita
    #   o relatório. Falhas definitivas são reservadas para corrupção de dados confirmada
    #   (campos obrigatórios ausentes). Uma discrepância entre summary e componentes pode
    #   simplesmente significar que o LLM usou sinônimos ou abreviações, então a rejeição
    #   seria desnecessariamente rígida. .lower() normaliza ambos os lados para que
    #   "API Gateway" e "api gateway" sejam considerados iguais.
    summary_lower = report.summary.lower()
    mentioned = any(c.name.lower() in summary_lower for c in report.components)
    if not mentioned:
        logger.warning(
            "Summary does not mention any identified component — possible hallucination",
            extra={
                "event": "semantic_guardrail_summary_mismatch",
                "analysis_id": analysis_id,
                "details": {"component_names": list(component_names)},
            },
        )

    return report


# ── Etapas do pipeline ───────────────────────────────────────────────────────

def _step_preprocess(
    file_bytes: bytes,
    filename: str,
    analysis_id: str,
) -> tuple[bytes, str]:
    """Valida e normaliza o arquivo enviado para uma imagem PNG.

    Delega a :func:`~ai_module.core.preprocessor.preprocess` para
    detecção de formato e conversão de imagem. Registra temporização e detalhes de erros.

    Parameters
    ----------
    file_bytes : bytes
        Bytes brutos do arquivo enviado.
    filename : str
        Nome original do arquivo (usado apenas para logging).
    analysis_id : str
        Identificador de correlação para os logs estruturados.

    Returns
    -------
    tuple[bytes, str]
        ``(image_bytes, input_type)`` onde *image_bytes* é o PNG
        normalizado e *input_type* é ``"image"`` ou ``"pdf"``.

    Raises
    ------
    UnsupportedFormatError
        Quando o tipo de arquivo não é PNG, JPEG ou PDF.
    InvalidInputError
        Quando o arquivo está vazio ou excede o limite de tamanho.
    """
    logger.info(
        "Preprocessing started",
        extra={
            "event": "preprocessing_start",
            "analysis_id": analysis_id,
            "details": {"filename": filename},
        },
    )
    # Nota 11: time.monotonic() registra o relógio antes do pré-processamento começar.
    #   O tempo decorrido é calculado depois como (time.monotonic() - pre_start) * 1000
    #   para converter segundos em milissegundos. Valores do relógio monotônico nunca
    #   diminuem dentro de um processo, então a medição é precisa mesmo que uma
    #   sincronização NTP ajuste o relógio do sistema durante a requisição — cenário
    #   onde time.time() poderia produzir um delta negativo.
    pre_start = time.monotonic()
    try:
        image_bytes, input_type = preprocess(file_bytes, filename)
    except (UnsupportedFormatError, InvalidInputError) as e:
        logger.error(
            "Preprocessing failed",
            extra={
                "event": "preprocessing_error",
                "analysis_id": analysis_id,
                "details": {
                    "error_code": type(e).__name__,
                    "message": e.message,
                    "filename": filename,
                    "file_size_bytes": len(file_bytes),
                    "file_signature_hex": _file_signature_hex(file_bytes),
                },
            },
        )
        raise

    pre_ms = int((time.monotonic() - pre_start) * 1000)
    logger.info(
        "Preprocessing completed",
        extra={
            "event": "preprocessing_success",
            "analysis_id": analysis_id,
            "details": {
                "processing_time_ms": pre_ms,
                "input_type": input_type,
                "normalized_image_size_bytes": len(image_bytes),
            },
        },
    )
    return image_bytes, input_type


def _step_build_prompts(image_bytes: bytes, analysis_id: str) -> tuple[str, str]:
    """Constrói os prompts de sistema e de usuário para o LLM.

    O prompt de usuário incorpora a imagem codificada em base 64 e o esquema JSON
    que o LLM deve seguir ao produzir o relatório.

    Parameters
    ----------
    image_bytes : bytes
        Bytes da imagem PNG normalizada.
    analysis_id : str
        Identificador de correlação para os logs estruturados.

    Returns
    -------
    tuple[str, str]
        ``(system_prompt, user_prompt)``.
    """
    # Nota 12: A API do LLM usa um modelo de dois prompts: o prompt de sistema define o
    #   papel do agente e o esquema JSON de saída (constante entre requisições); o prompt
    #   de usuário carrega o payload por requisição (a imagem em base64 e a instrução de
    #   análise). O underscore (_) descarta o segundo valor de retorno de build_user_prompt
    #   (a string base64 bruta), necessário apenas para adaptadores que enviam imagens
    #   separadamente.
    system_prompt = build_system_prompt()
    user_prompt, _ = build_user_prompt(image_bytes)
    logger.info(
        "Prompts built",
        extra={
            "event": "prompt_build_success",
            "analysis_id": analysis_id,
            "details": {
                "system_prompt_length": len(system_prompt),
                "user_prompt_length": len(user_prompt),
            },
        },
    )
    return system_prompt, user_prompt


async def _step_call_llm(
    adapter: LLMAdapter,
    image_bytes: bytes,
    current_prompt: str,
    system_prompt: str,
    analysis_id: str,
    attempt: int,
) -> str:
    """Envia uma única requisição ao provedor LLM configurado.

    Encapsula ``adapter.analyze`` com logging estruturado para eventos de
    início, sucesso, timeout e erro.

    Parameters
    ----------
    adapter : LLMAdapter
        Adaptador específico do provedor (Gemini ou OpenAI).
    image_bytes : bytes
        Bytes da imagem PNG normalizada.
    current_prompt : str
        Prompt de usuário (pode ser o original ou um prompt de correção).
    system_prompt : str
        Prompt de instrução em nível de sistema.
    analysis_id : str
        Identificador de correlação para os logs estruturados.
    attempt : int
        Número da tentativa atual (base 1).

    Returns
    -------
    str
        Resposta textual bruta do LLM.

    Raises
    ------
    LLMTimeoutError
        Quando o provedor não responde dentro da janela de timeout.
    LLMCallError
        Quando o provedor retorna um erro irrecuperável.
    """
    logger.info(
        "LLM call started",
        extra={
            "event": "llm_call_start",
            "analysis_id": analysis_id,
            "details": {
                "attempt": attempt,
                "provider": _PROVIDER,
                "model": settings.LLM_MODEL,
                "image_size_bytes": len(image_bytes),
            },
        },
    )
    # Nota 13: 'await adapter.analyze(...)' suspende esta coroutine na fronteira de rede
    #   e cede o controle ao event loop do asyncio enquanto aguarda a resposta HTTP do
    #   provedor LLM (tipicamente 2–20 segundos). Durante essa suspensão, o event loop
    #   processa outras coroutines — health checks, endpoints de métricas ou outras
    #   requisições em andamento — sem bloquear a thread do SO.
    llm_start = time.monotonic()

    try:
        raw = await adapter.analyze(image_bytes, current_prompt, system_prompt)
    # Nota 14: LLMTimeoutError é uma condição transitória e recuperável (latência de rede,
    #   lentidão do provedor) e é registrada em WARNING para evitar alertas espúrios.
    #   LLMCallError reflete uma falha mais grave (chave de API inválida, cota excedida,
    #   erro de modelo) e é registrada em ERROR. Separá-los permite alertas precisos:
    #   engenheiros de plantão configuram regras de alerta em eventos ERROR e tratam
    #   picos de WARNING como informativos.
    except LLMTimeoutError as e:
        logger.warning(
            "LLM call timed out",
            extra={
                "event": "llm_call_timeout",
                "analysis_id": analysis_id,
                "details": {
                    "attempt": attempt,
                    "timeout_seconds": settings.LLM_TIMEOUT_SECONDS,
                    "message": e.message,
                },
            },
        )
        raise
    except LLMCallError as e:
        logger.error(
            "LLM call failed",
            extra={
                "event": "llm_call_error",
                "analysis_id": analysis_id,
                "details": {
                    "attempt": attempt,
                    "error_type": type(e).__name__,
                    "message": e.message,
                },
            },
        )
        raise

    llm_ms = int((time.monotonic() - llm_start) * 1000)
    logger.info(
        "LLM call succeeded",
        extra={
            "event": "llm_call_success",
            "analysis_id": analysis_id,
            "details": {
                "attempt": attempt,
                "processing_time_ms": llm_ms,
                "model_used": settings.LLM_MODEL,
                "raw_response_length": len(raw),
            },
        },
    )
    return raw


def _step_validate(raw: str, analysis_id: str, attempt: int) -> tuple[Report, dict]:
    """Analisa e valida a resposta bruta do LLM em um ``Report``.

    Delega a :func:`~ai_module.core.report_validator.validate_and_normalize`
    que extrai o JSON, aplica o esquema Pydantic e normaliza os campos
    (ex.: truncamento do summary).

    Parameters
    ----------
    raw : str
        Texto bruto retornado pelo LLM.
    analysis_id : str
        Identificador de correlação para os logs estruturados.
    attempt : int
        Número da tentativa atual (base 1).

    Returns
    -------
    tuple[Report, dict]
        ``(report, metadata_flags)`` onde *metadata_flags* contém
        indicadores de pós-processamento como ``summary_truncated``.

    Raises
    ------
    ValueError
        Quando a resposta não pode ser analisada ou viola o esquema.
    """
    # Nota 15: validate_and_normalize extrai o JSON da resposta do LLM (removendo cercas
    #   de código markdown se presentes), valida contra o esquema Pydantic Report
    #   (verificação de tipos e restrições) e normaliza os campos (ex.: truncando
    #   summaries muito longos). Mensagens de ValueError começam com uma palavra-chave
    #   como JSON_PARSE_ERROR, que _classify_validation_error usa para escolher a correção.
    try:
        report, metadata_flags = validate_and_normalize(raw)
    except ValueError as e:
        logger.warning(
            "Validation failed for LLM response",
            extra={
                "event": "validation_error",
                "analysis_id": analysis_id,
                "details": {
                    "attempt": attempt,
                    "error": _truncate_for_log(str(e), limit=300),
                    "raw_response_excerpt": _truncate_for_log(raw),
                },
            },
        )
        raise

    logger.info(
        "Report validation succeeded",
        extra={
            "event": "validation_success",
            "analysis_id": analysis_id,
            "details": {
                "attempt": attempt,
                "summary_truncated": metadata_flags["summary_truncated"],
                "components_count": len(report.components),
                "risks_count": len(report.risks),
                "recommendations_count": len(report.recommendations),
            },
        },
    )
    return report, metadata_flags


async def _step_retry_loop(
    adapter: LLMAdapter,
    image_bytes: bytes,
    system_prompt: str,
    user_prompt: str,
    analysis_id: str,
) -> tuple[Report, dict, int]:
    """Reexecuta o ciclo de chamada ao LLM + validação até ``LLM_MAX_RETRIES`` vezes.

    Em caso de falha de validação, o LLM recebe um *prompt de correção* que
    inclui a resposta bruta anterior e o erro de validação para que possa
    se autocorrigir. Erros de timeout e de chamada simplesmente avançam para
    a próxima tentativa.

    Parameters
    ----------
    adapter : LLMAdapter
        Adaptador específico do provedor.
    image_bytes : bytes
        Bytes da imagem PNG normalizada.
    system_prompt : str
        Prompt de instrução em nível de sistema.
    user_prompt : str
        Prompt de usuário inicial (usado na primeira tentativa).
    analysis_id : str
        Identificador de correlação para os logs estruturados.

    Returns
    -------
    tuple[Report, dict, int]
        ``(report, metadata_flags, successful_attempt)``.

    Raises
    ------
    AIFailureError
        Quando todas as tentativas são esgotadas sem produzir um relatório válido.
    """
    # Nota 16: Variáveis de estado com escopo neste frame de função. current_prompt começa
    #   como o user_prompt original e é sobrescrito a cada tentativa falha por um prompt
    #   de correção que incorpora a resposta bruta anterior e a mensagem de erro.
    #   last_raw e last_error carregam o contexto de falha entre iterações para que o
    #   construtor de prompts de correção possa referenciá-los. successful_attempt é None
    #   até que um relatório válido seja produzido, funcionando como flag de sucesso e
    #   contador de tentativas.
    report: Report | None = None
    metadata_flags: dict = {"summary_truncated": False}
    current_prompt = user_prompt
    last_raw: str = ""
    last_error: str = ""
    successful_attempt: int | None = None

    # Nota 17: range(1, LLM_MAX_RETRIES + 1) produz inteiros de base 1 (1, 2, 3...).
    #   Base 1 é preferida para mensagens de log ("tentativa 1 de 3") em vez de base 0.
    #   LLM_MAX_RETRIES é lido de settings (variável de ambiente), então o orçamento de
    #   retentativas pode ser ajustado por implantação sem modificar o código — princípio
    #   central da metodologia 12-Factor App ("armazene a configuração no ambiente").
    for attempt in range(1, settings.LLM_MAX_RETRIES + 1):
        if attempt > 1 and last_raw and last_error:
            targeted_instruction = _classify_validation_error(last_error)
            current_prompt = build_correction_prompt(last_raw, targeted_instruction)
            logger.info(
                "Prepared targeted correction prompt",
                extra={
                    "event": "correction_prompt_built",
                    "analysis_id": analysis_id,
                    "details": {
                        "attempt": attempt,
                        "error_class": targeted_instruction[:80],
                    },
                },
            )

        try:
            raw = await _step_call_llm(
                adapter, image_bytes, current_prompt, system_prompt, analysis_id, attempt,
            )
        except (LLMTimeoutError, LLMCallError):
            # Nota 18: Ambos os tipos de erro resultam na mesma ação de recuperação (avançar
            #   para a próxima tentativa), então são agrupados em uma única cláusula except.
            #   Isso evita duplicar o continue e torna explícita a intenção de recuperação
            #   compartilhada. Python permite qualquer número de tipos de exceção em uma
            #   tupla except quando o tratamento é idêntico — frequentemente chamado de
            #   idioma "multi-catch".
            continue

        try:
            report, metadata_flags = _step_validate(raw, analysis_id, attempt)
        except ValueError as e:
            last_raw = raw
            last_error = str(e)
            continue

        report = _apply_semantic_guardrails(report, analysis_id)
        successful_attempt = attempt
        # Nota 19: break sai do for-loop na primeira iteração onde tanto a chamada ao LLM
        #   quanto a validação são bem-sucedidas. Sem break, o loop continuaria para a
        #   próxima tentativa desnecessariamente. successful_attempt é definido antes do
        #   break para que run_pipeline possa calcular o total de retentativas como
        #   (successful_attempt - 1) e atualizar o contador llm_retries_total abaixo.
        break

    if report is None or successful_attempt is None:
        logger.error(
            "Analysis failed after all retries",
            extra={
                "event": "analysis_failure",
                "analysis_id": analysis_id,
                "details": {
                    "error_code": "AI_FAILURE",
                    "provider": _PROVIDER,
                    "model": settings.LLM_MODEL,
                    "last_error": _truncate_for_log(last_error, limit=300) if last_error else None,
                    "last_raw_response_excerpt": _truncate_for_log(last_raw) if last_raw else None,
                },
            },
        )
        metrics.requests_error += 1
        raise AIFailureError("Failed to generate a valid report after all retries.")

    return report, metadata_flags, successful_attempt


def _build_response(
    report: Report,
    analysis_id: str,
    input_type: str,
    total_ms: int,
) -> AnalyzeResponse:
    """Monta a resposta final da API com o relatório e metadados.

    Parameters
    ----------
    report : Report
        Relatório de análise validado.
    analysis_id : str
        Identificador de correlação.
    input_type : str
        Tipo original do arquivo (``"image"`` ou ``"pdf"``).
    total_ms : int
        Tempo total de parede do pipeline em milissegundos.

    Returns
    -------
    AnalyzeResponse
        Modelo de resposta serializável.
    """
    # Nota 20: Padrão de função fábrica — _build_response encapsula a construção de
    #   AnalyzeResponse e a isola da lógica de orquestração em run_pipeline. Testes
    #   unitários podem chamar esta função diretamente com um Report mockado sem executar
    #   o pipeline completo. Isso mantém run_pipeline legível como um script de alto nível,
    #   em vez de misturar chamadas de construtor com etapas de orquestração.
    return AnalyzeResponse(
        analysis_id=analysis_id,
        status="success",
        report=report,
        metadata=ReportMetadata(
            model_used=settings.LLM_MODEL,
            processing_time_ms=total_ms,
            input_type=input_type,  # type: ignore[arg-type]
        ),
    )


# ── Ponto de entrada ─────────────────────────────────────────────────────────

async def run_pipeline(
    file_bytes: bytes,
    filename: str,
    analysis_id: str,
    adapter: LLMAdapter,
) -> AnalyzeResponse:
    """Executa o pipeline completo de análise de ponta a ponta.

    Orquestra pré-processamento → construção de prompts → loop de retentativas do LLM →
    montagem da resposta, atualizando as métricas globais em cada etapa.

    Parameters
    ----------
    file_bytes : bytes
        Bytes brutos do arquivo enviado.
    filename : str
        Nome original do arquivo.
    analysis_id : str
        UUID4 único identificando esta requisição.
    adapter : LLMAdapter
        Adaptador específico do provedor resolvido pelo handler de rota.

    Returns
    -------
    AnalyzeResponse
        Resposta completa incluindo o relatório validado e metadados.

    Raises
    ------
    UnsupportedFormatError
        Propagado do pré-processamento.
    InvalidInputError
        Propagado do pré-processamento.
    AIFailureError
        Quando o LLM falha em produzir um relatório válido após todas as tentativas.
    """
    logger.info(
        "Analysis request received",
        extra={
            "event": "request_received",
            "analysis_id": analysis_id,
            "details": {
                "filename": filename,
                "file_size_bytes": len(file_bytes),
                "provider": _PROVIDER,
                "model": settings.LLM_MODEL,
            },
        },
    )
    # Nota 21: A temporização de ponta a ponta começa aqui, imediatamente após o registro
    #   de log de entrada. O total_ms final é incluído tanto no corpo da resposta da API
    #   quanto no log de conclusão, habilitando monitoramento de SLA: operadores podem
    #   comparar a latência da requisição observada pelo cliente com o total_ms reportado
    #   pelo servidor para isolar se o gargalo é sobrecarga de rede ou processamento
    #   no servidor.
    total_start = time.monotonic()

    # Nota 22: O pipeline é decomposto em funções nomeadas _step_*. Esse padrão de estágios
    #   mantém run_pipeline legível como um script de orquestração linear e permite que
    #   cada estágio seja testado unitariamente ou perfilado de forma independente. 'await'
    #   aparece apenas antes de _step_retry_loop porque é o único estágio que realiza
    #   I/O de rede (a requisição HTTP ao LLM); pré-processamento e construção de prompts
    #   executam de forma síncrona.
    image_bytes, input_type = _step_preprocess(file_bytes, filename, analysis_id)
    system_prompt, user_prompt = _step_build_prompts(image_bytes, analysis_id)
    report, _flags, successful_attempt = await _step_retry_loop(
        adapter, image_bytes, system_prompt, user_prompt, analysis_id,
    )

    # Nota 23: Os contadores de métricas são incrementados apenas no caminho de sucesso —
    #   este bloco é inalcançável se qualquer função _step_* lançar uma exceção. Na
    #   implantação atual de worker único do uvicorn, a mutação direta de inteiros está
    #   livre de condições de corrida. Uma implantação multi-processo ou multi-thread
    #   exigiria atômicos thread-safe ou um armazenamento externo (ex.: statsd, um
    #   Prometheus push gateway ou Redis).
    metrics.requests_success += 1
    metrics.llm_retries_total += successful_attempt - 1

    total_ms = int((time.monotonic() - total_start) * 1000)
    metrics.processing_time_ms_total += total_ms

    logger.info(
        "Analysis completed successfully",
        extra={
            "event": "analysis_success",
            "analysis_id": analysis_id,
            "details": {"total_time_ms": total_ms, "input_type": input_type},
        },
    )

    return _build_response(report, analysis_id, input_type, total_ms)