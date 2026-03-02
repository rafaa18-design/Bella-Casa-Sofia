# Execucao Assincrona

Todo o pipeline do agente e assincrono. O agent loop usa `litellm.acompletion()`, o FastAPI lida com requests async nativamente, e a consolidacao de memoria roda como background task via `asyncio.create_task()`.

---

## Visao Geral

| Componente | Funcao Async | Arquivo |
|------------|-------------|---------|
| **Agent Loop** | `run_agent_loop()` | `app/agent_loop.py` |
| **LLM Calls** | `litellm.acompletion()` | `app/agent_loop.py` |
| **Tool Execution** | `ToolRegistry.execute()` | `app/runtime.py` |
| **Consolidacao** | `consolidate()` via `asyncio.create_task()` | `app/memory.py` |
| **Storage (Redis)** | `get_session_state()`, `add_message_to_history()` | `app/storage.py` |
| **Endpoints** | `async def run()`, `async def run_debug()` | `app/main.py` |

---

## Agent Loop Assincrono

O `run_agent_loop()` em `app/agent_loop.py` e a funcao central do pipeline. Ele executa um loop iterativo de tool-calling usando `litellm.acompletion()`:

```python
async def run_agent_loop(
    messages: list[dict],
    tools: ToolRegistry,
    run_context: RunContext,
    model: str,
    max_iterations: int = 10,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> AgentResponse:
    """Executa o agent loop com litellm."""
    total_input_tokens = 0
    total_output_tokens = 0
    tools_used: list[str] = []
    tool_definitions = tools.get_definitions()

    for iteration in range(max_iterations):
        # Chamada assincrona ao LLM
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            tools=tool_definitions if tool_definitions else None,
            tool_choice='auto' if tool_definitions else None,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        message = response.choices[0].message

        # Se nao ha tool_calls, temos a resposta final
        if not message.tool_calls:
            return AgentResponse(
                content=message.content or '',
                messages=messages,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                tools_used=tools_used,
                session_state=run_context.session_state,
            )

        # Executa cada tool call e adiciona resultados
        for tc in message.tool_calls:
            result = await tools.execute(tc.function.name, args, run_context)
            messages.append({
                'role': 'tool',
                'tool_call_id': tc.id,
                'content': result,
            })
        # Loop continua com os resultados das tools...
```

### Fluxo do Loop

```
litellm.acompletion()
    |
    +-- tool_calls? Sim --> ToolRegistry.execute() --> adiciona resultados --> repete
    |
    +-- tool_calls? Nao --> retorna AgentResponse(content=...)
    |
    +-- RetryAgentRun  --> feedback como tool result, continua loop
    +-- StopAgentRun   --> para loop imediatamente
    |
    +-- max_iterations atingido --> retorna com mensagem de limite
```

---

## Endpoints FastAPI (Nativamente Async)

Os endpoints do FastAPI sao `async def`, o que significa que o event loop do asyncio gerencia concorrencia automaticamente:

```python
@agentbench_router.post('/run', response_model=RunResponse)
async def run(request: RunRequest) -> RunResponse:
    """Endpoint de producao -- totalmente assincrono."""
    result = await execute_agent(request, debug=False)

    message = extract_response_text(result.response) if result.response else ''

    return RunResponse(
        conversation_id=request.conversation_id,
        final_output=FinalOutput(
            message=message,
            state=result.session_state if result.session_state else None,
            actions_taken=result.actions if result.actions else None,
        ),
        metrics=Metrics(
            latency_ms=result.latency_ms,
            tokens_used=result.input_tokens + result.output_tokens,
        ),
    )
```

### Execucao do Agente (execute_agent)

A funcao `execute_agent()` em `app/main.py` orquestra todo o pipeline async:

```python
async def execute_agent(request: RunRequest, debug: bool = False) -> AgentRunResult:
    """Executa o agente e retorna resultado unificado."""
    start_time = time.perf_counter()

    # 1. Parse multimodal input
    text_message, images = parse_multimodal_input(request.input)

    # 2. Buscar estado da sessao (Redis, async)
    session_state = await get_session_state(conversation_id)

    # 3. Buscar instrucoes do prompt (Langfuse/cache)
    template = await get_agent_instructions()

    # 4. Buscar contexto de memoria (Redis, async)
    memory_context = await get_memory_context(conversation_id)

    # 5. Buscar historico de conversa (Redis, async)
    history = await get_message_history(conversation_id)

    # 6. Montar mensagens e executar agent loop
    messages = build_system_messages(instructions, text_message, images, history)
    response = await run_agent_loop(
        messages=messages,
        tools=registry,
        run_context=run_context,
        model=model,
    )

    # 7. Salvar historico (Redis, async)
    await add_message_to_history(conversation_id, 'user', text_message)
    await add_message_to_history(conversation_id, 'assistant', response_text)

    # 8. Agendar consolidacao de memoria (background task)
    if settings.MEMORY_CONSOLIDATION_ENABLED:
        await increment_unconsolidated(conversation_id)
        if await should_consolidate(conversation_id):
            schedule_consolidation(conversation_id)  # asyncio.create_task()

    return AgentRunResult(...)
```

---

## Consolidacao de Memoria em Background

A consolidacao de memoria e a operacao async mais importante alem do agent loop. Ela roda como background task para nao bloquear a resposta ao usuario:

```python
# app/memory.py
def schedule_consolidation(cid: str) -> None:
    """Agenda consolidacao como background task com lock por sessao."""
    async def _run():
        if cid not in _consolidation_locks:
            _consolidation_locks[cid] = asyncio.Lock()

        lock = _consolidation_locks[cid]
        if lock.locked():
            logger.debug(f'Consolidacao ja rodando para {cid}, pulando')
            return

        async with lock:
            await consolidate(cid)

    task = asyncio.create_task(_run())
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)
```

### Consolidacao Interna (consolidate)

A funcao `consolidate()` faz uma chamada LLM assincrona com um modelo mais barato para resumir o historico:

```python
async def consolidate(cid: str) -> None:
    """Consolidacao LLM-driven de memoria."""
    client = await get_redis()

    # Buscar fatos existentes e historico recente
    existing_facts = await client.get(_facts_key(cid)) or ''
    history = await get_message_history(cid, limit=settings.MEMORY_WINDOW * 2)

    # Chamar LLM para consolidar
    response = await litellm.acompletion(
        model=model,
        messages=[
            {'role': 'system', 'content': _CONSOLIDATION_SYSTEM_PROMPT},
            {'role': 'user', 'content': user_message},
        ],
        tools=[_SAVE_MEMORY_TOOL],
        tool_choice={'type': 'function', 'function': {'name': 'save_memory'}},
        max_tokens=settings.MEMORY_CONSOLIDATION_MAX_TOKENS,
    )

    # Extrair e salvar fatos atualizados
    # ... (processa tool call save_memory)
    await client.set(_facts_key(cid), memory_update, ex=settings.REDIS_SESSION_TTL)
    await client.set(_unconsolidated_key(cid), 0, ex=settings.REDIS_SESSION_TTL)
```

### Protecoes da Consolidacao

| Protecao | Mecanismo |
|----------|-----------|
| **Lock por sessao** | `asyncio.Lock()` por `cid` evita consolidacoes concorrentes |
| **Rastreamento de tasks** | `_active_tasks` set permite aguardar no shutdown |
| **Graceful shutdown** | `shutdown_consolidation()` aguarda tasks ativas |
| **Modelo barato** | Usa `MEMORY_CONSOLIDATION_MODEL` (ex: `claude-haiku-4-5-20251001`) |

---

## Graceful Shutdown

O lifecycle do FastAPI gerencia shutdown assincrono, aguardando requests em andamento e tasks de consolidacao:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup...
    yield

    # Graceful shutdown
    logger.info('Iniciando graceful shutdown...')
    shutdown_start = asyncio.get_event_loop().time()
    timeout = settings.SHUTDOWN_TIMEOUT

    # Aguardar requests em andamento
    while get_active_requests() > 0:
        elapsed = asyncio.get_event_loop().time() - shutdown_start
        if elapsed >= timeout:
            break
        await asyncio.sleep(1)

    # Aguardar consolidacoes ativas
    await shutdown_consolidation(timeout=5.0)

    # Fechar recursos
    shutdown_tracing()
    await close_redis()
    langfuse_shutdown()
```

A funcao `shutdown_consolidation()` usa `asyncio.wait()` com timeout:

```python
async def shutdown_consolidation(timeout: float = 10.0) -> None:
    """Aguarda tasks de consolidacao ativas durante shutdown."""
    if not _active_tasks:
        return

    done, pending = await asyncio.wait(_active_tasks, timeout=timeout)
    if pending:
        for task in pending:
            task.cancel()
```

---

## Timeout com asyncio

Para operacoes que precisam de timeout explicito, use `asyncio.wait_for()`:

```python
import asyncio

async def run_with_timeout(request: RunRequest, timeout_seconds: float = 60.0):
    """Executa agente com timeout."""
    try:
        result = await asyncio.wait_for(
            execute_agent(request),
            timeout=timeout_seconds,
        )
        return result
    except asyncio.TimeoutError:
        return AgentRunResult(
            response=None,
            instructions='',
            session_state={},
            latency_ms=timeout_seconds * 1000,
            input_tokens=0,
            output_tokens=0,
            text_message='',
            actions=[],
            error=TimeoutError(f'Execucao excedeu {timeout_seconds}s'),
        )
```

---

## Concorrencia entre Requests

O FastAPI com uvicorn roda em um unico event loop asyncio. Multiplas requests sao processadas concorrentemente (nao em paralelo -- e concorrencia cooperativa):

```
Request A --> await execute_agent() --> await litellm.acompletion() [aguardando I/O]
                                            |
Request B --> await execute_agent() ------->| executa enquanto A aguarda
                                            |
Request A <-- resposta do LLM <-------------|
```

Cada request mantem seu proprio `RunContext`, `session_state` e `conversation_id`, entao nao ha compartilhamento de estado entre requests.

---

## Resumo do Pipeline Async

```
POST /run (FastAPI async handler)
    |
    v
execute_agent() [async]
    |-- parse_multimodal_input()           [sync, CPU-bound rapido]
    |-- await get_session_state()          [async, Redis I/O]
    |-- await get_agent_instructions()     [async, cache/Langfuse]
    |-- await get_memory_context()         [async, Redis I/O]
    |-- await get_message_history()        [async, Redis I/O]
    |-- build_system_messages()            [sync, montagem de dicts]
    |-- await run_agent_loop()             [async, multiplas chamadas LLM]
    |   |-- await litellm.acompletion()    [async, HTTP ao provider]
    |   |-- await tools.execute()          [async, execucao de tools]
    |   |-- (repete ate resposta final)
    |-- await add_message_to_history()     [async, Redis I/O]
    |-- await update_session_state()       [async, Redis I/O]
    |-- schedule_consolidation()           [asyncio.create_task(), nao bloqueia]
    |
    v
RunResponse (retornado ao cliente)
```

---

## Referencias

- [asyncio Documentation](https://docs.python.org/3/library/asyncio.html)
- [FastAPI Async](https://fastapi.tiangolo.com/async/)
- [LiteLLM Async Completion](https://docs.litellm.ai/docs/completion/reliable_completions#async-completion)
- [Uvicorn](https://www.uvicorn.org/)
