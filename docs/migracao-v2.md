# Guia de Migração: Template Agno (v1) → LiteLLM (v2)

Este guia detalha como migrar uma aplicação existente baseada no template antigo (Agno) para a nova versão (LiteLLM + agent loop customizado).

---

## Visão Geral das Mudanças

| Aspecto | v1 (Agno) | v2 (LiteLLM) |
|---------|-----------|--------------|
| **Framework** | `agno==2.4.6` (framework completo) | `litellm>=1.55.0` + agent loop próprio |
| **Agent loop** | Black-box dentro de `Agent.run()` | Transparente em `run_agent_loop()` |
| **Modelos** | Classes Agno (`Claude`, `OpenAIChat`) | Strings litellm (`"anthropic/claude-..."`) |
| **Tools** | `from agno.tools import tool` | `from app.runtime import tool` |
| **Memória** | Agno built-in (opaco) | Consolidação LLM-driven (transparente) |
| **main.py** | Monolítico (1300+ linhas) | Modular (~175 linhas + `app/routes/`) |
| **Middleware** | `agno.os.middleware.jwt` | `app.middleware` customizado |
| **Observabilidade** | 3 arquivos separados | Unificado em `app/observability.py` |
| **Tools (arquivos)** | 1 arquivo por tool (13 arquivos) | Agrupados por domínio (4 arquivos) |

---

## Passo 1: Atualizar Dependências

### pyproject.toml

**Remover:**
```toml
"agno==2.4.6",
"openinference-instrumentation-agno>=0.1.28",
```

**Adicionar:**
```toml
"litellm>=1.55.0",
"json-repair>=0.30.0",
```

O restante das dependências permanece idêntico.

**Executar:**
```bash
uv sync
```

---

## Passo 2: Adicionar `app/runtime.py` (NOVO)

Este é o módulo que substitui todos os imports do Agno. Copie integralmente o `app/runtime.py` da nova versão.

Ele fornece:

| Componente | Substitui |
|------------|-----------|
| `RunContext` | `agno.run.RunContext` |
| `RetryAgentRun` | `agno.exceptions.RetryAgentRun` |
| `StopAgentRun` | `agno.exceptions.StopAgentRun` |
| `@tool` decorator | `agno.tools.tool` |
| `ToolRegistry` | Registro interno do Agno |
| `ToolDefinition` | Formato interno do Agno |

---

## Passo 3: Migrar Tools

### 3.1 Atualizar imports

A mudança principal nas tools é **apenas na linha de import**. A lógica permanece idêntica.

**ANTES (v1):**
```python
from agno.exceptions import RetryAgentRun
from agno.run import RunContext
from agno.tools import tool
```

**DEPOIS (v2):**
```python
from app.runtime import RetryAgentRun, RunContext, tool
```

A assinatura das funções, docstrings, uso de `run_context.session_state` e `RetryAgentRun` — tudo continua igual.

### 3.2 (Opcional) Agrupar tools por domínio

A v2 agrupa tools em arquivos por domínio para reduzir file bloat:

| Antes (v1) | Depois (v2) |
|------------|-------------|
| `agendar_consulta.py` | `consultas.py` |
| `cancelar_consulta.py` | `consultas.py` |
| `verificar_disponibilidade.py` | `consultas.py` |
| `buscar_paciente.py` | `pacientes.py` |
| `consultar_historico.py` | `pacientes.py` |
| `verificar_cliente.py` | `pacientes.py` |
| `consultar_convenios.py` | `pacientes.py` |
| `listar_servicos.py` | `catalogo.py` |
| `calcular_orcamento.py` | `catalogo.py` |
| `obter_data_hora.py` | `catalogo.py` |
| `salvar_dados_cliente.py` | `sessao.py` |
| `salvar_preferencias.py` | `sessao.py` |
| `ver_contexto_sessao.py` | `sessao.py` |

Este passo é opcional — a v2 funciona com arquivos individuais também.

### 3.3 Atualizar `app/tools/__init__.py`

Atualize os imports conforme a nova organização. A v2 mantém os mesmos nomes de função exportados:

```python
from app.tools.catalogo import calcular_orcamento, listar_servicos, obter_data_hora
from app.tools.consultas import agendar_consulta, cancelar_consulta, verificar_disponibilidade
from app.tools.formatar_contexto import formatar_contexto_completo, formatar_contexto_state
from app.tools.pacientes import (
    buscar_paciente,
    consultar_convenios,
    consultar_historico_paciente,
    verificar_cliente,
)
from app.tools.sessao import salvar_dados_cliente, salvar_preferencias, ver_contexto_sessao
```

---

## Passo 4: Reescrever `app/agent.py`

A mudança mais significativa da migração. O Agno encapsulava tudo — agora é explícito.

### ANTES (v1) — Factory de agente Agno

```python
from agno.agent import Agent
from agno.models.anthropic import Claude
from agno.models.openai import OpenAIChat

def get_model(model_id):
    if 'claude' in model_id.lower():
        return Claude(id=model_id, api_key=settings.ANTHROPIC_API_KEY)
    if 'gpt' in model_id.lower():
        return OpenAIChat(id=model_id)

def create_agent(model_id, session_id, user_id, instructions) -> Agent:
    return Agent(
        name=settings.AGENT_NAME,
        model=get_model(model_id),
        tools=[listar_servicos, agendar_consulta, ...],
        instructions=instructions,
        session_id=session_id,
        user_id=user_id,
        add_history_to_context=True,
        num_history_runs=settings.NUM_HISTORY_RUNS,
        compress_tool_results=settings.COMPRESS_TOOL_RESULTS,
        tool_call_limit=settings.TOOL_CALL_LIMIT,
    )
```

### DEPOIS (v2) — Funções utilitárias + agent loop customizado

O novo `app/agent.py` contém:

1. **`get_litellm_model(model_id)`** — Converte ID do modelo para string litellm
2. **`get_tools_registry()`** — Registra todas as tools em um `ToolRegistry`
3. **`build_system_messages()`** — Constrói array de mensagens (system + history + user)
4. **`run_agent_loop()`** — Loop iterativo de tool-calling com litellm

```python
import litellm
from app.runtime import RunContext, ToolRegistry

litellm.drop_params = True  # Compatibilidade cross-provider

def get_litellm_model(model_id: str | None = None) -> str:
    model_id = model_id or settings.DEFAULT_MODEL
    if 'claude' in model_id.lower():
        return f'anthropic/{model_id}'
    if 'gpt' in model_id.lower() or 'o1' in model_id.lower():
        return f'openai/{model_id}'
    if '@' in model_id or settings.MODEL_PROVIDER == 'vertexai':
        return f'vertex_ai/{model_id}'
    return model_id

def get_tools_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_def in [listar_servicos, agendar_consulta, ...]:
        registry.register(tool_def)
    return registry

async def run_agent_loop(messages, tools, run_context, model, ...) -> AgentResponse:
    # Loop: litellm.acompletion() → tool_calls → execute → repeat
    for iteration in range(max_iterations):
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            tools=tool_definitions,
            tool_choice='auto',
        )
        if not message.tool_calls:
            return AgentResponse(content=message.content, ...)
        # Execute tools, add results to messages, continue...
```

Copie integralmente o `app/agent.py` da v2. Ele inclui otimizações:

- **Prompt caching** para modelos Anthropic (`cache_control: ephemeral`)
- **Deduplicação de tool calls** (hash MD5 de nome + args)
- **Limite por tool** (max 3 chamadas da mesma tool por turno)
- **Execução paralela** de tools (`asyncio.gather`)

---

## Passo 5: Migrar `execute_agent()` no fluxo de execução

### ANTES (v1) — Chamada ao Agno

```python
agent = create_agent(model_id, session_id, user_id, instructions)
response = await agent.run(
    message=text_message,
    images=images,
    audios=audios,
)
text_output = extract_response_text(response)
```

### DEPOIS (v2) — Chamada ao agent loop

```python
from app.agent import build_system_messages, get_litellm_model, get_tools_registry, run_agent_loop
from app.runtime import RunContext

# 1. Criar mensagens
messages = build_system_messages(instructions, text_message, images, history=history)

# 2. Criar contexto e registry
run_context = RunContext(session_state=session_state, session_id=cid, user_id=uid)
registry = get_tools_registry()
model = get_litellm_model(settings.DEFAULT_MODEL)

# 3. Executar loop
response = await run_agent_loop(
    messages=messages,
    tools=registry,
    run_context=run_context,
    model=model,
    max_iterations=settings.MAX_TURNS,
    max_tokens=settings.MAX_OUTPUT_TOKENS,
)

# 4. Extrair resultado
text_output = response.content
tools_used = response.tools_used
session_state = response.session_state
```

---

## Passo 6: Criar `app/middleware.py` (NOVO)

Consolida middlewares que antes estavam espalhados em `main.py` e `security.py`:

| Middleware | Origem na v1 |
|-----------|-------------|
| `RequestIDMiddleware` | Definido inline em `main.py` |
| `JWTAuthMiddleware` | `from agno.os.middleware.jwt import JWTMiddleware` |
| `SecurityHeadersMiddleware` | `app/security.py` |

Copie o `app/middleware.py` da v2. A `JWTAuthMiddleware` customizada substitui a do Agno com a mesma funcionalidade.

**Deletar** `app/security.py` (conteúdo migrou para `middleware.py`).

---

## Passo 7: Criar `app/observability.py` (NOVO)

Consolida 3 arquivos em 1:

| Arquivo v1 | Seção em `observability.py` |
|-----------|--------------------------|
| `app/logging_config.py` | Seção Logging (JSONFormatter, TextFormatter, setup_logging) |
| `app/tracing.py` | Seção Tracing (setup_tracing, shutdown_tracing) |
| `app/langfuse_client.py` | Seção Langfuse (get_langfuse, shutdown_langfuse) |

Copie o `app/observability.py` da v2 e **delete** os 3 arquivos antigos.

**Atualizar imports** em todo o projeto:

```python
# ANTES
from app.logging_config import setup_logging, request_id_var
from app.tracing import setup_tracing, shutdown_tracing
from app.langfuse_client import get_langfuse

# DEPOIS
from app.observability import setup_logging, request_id_var
from app.observability import setup_tracing, shutdown_tracing
from app.observability import get_langfuse, shutdown_langfuse
```

---

## Passo 8: Criar `app/memory.py` (NOVO)

A v2 introduz **consolidação de memória LLM-driven**, substituindo o sistema opaco do Agno.

### Como funciona

1. A cada mensagem, incrementa um contador `unconsolidated` no Redis
2. Quando `unconsolidated >= MEMORY_WINDOW`, um LLM barato consolida o histórico em fatos estruturados
3. Fatos ficam em `memory:{cid}:facts` no Redis e são injetados no system prompt
4. A consolidação roda em background (`asyncio.create_task`)

### Resiliência embutida

- Retry com exponential backoff (3 tentativas)
- Auto-escalação de `max_tokens` em caso de truncação (2048 → 4096 → 8192)
- Circuit breaker (3 falhas → OPEN por 60s)
- Cooldown exponencial entre falhas (30s → 300s cap)

### Novas variáveis de ambiente

```bash
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_WINDOW=20                        # Consolidar a cada 20 mensagens
MEMORY_CONSOLIDATION_MODEL=gpt-5-nano   # Modelo barato para consolidação
MEMORY_CONSOLIDATION_MAX_TOKENS=2048
```

Copie `app/memory.py` da v2.

---

## Passo 9: Extrair Rotas para `app/routes/` (NOVO)

Na v1, todas as rotas estavam em `main.py`. Na v2, são organizadas em sub-package:

```
app/routes/
├── __init__.py       # Re-exporta todos os routers
├── agentbench.py     # /metadata, /run, /run_debug
├── auth.py           # /auth/login, /auth/token
├── prompts.py        # /prompt/webhook, /prompt/refresh, /prompt/current
└── system.py         # /health, /metrics, /profiling, /
```

### O que extrair do main.py

| Router | Funções a extrair |
|--------|------------------|
| `agentbench_router` | `execute_agent()`, `parse_multimodal_input()`, `extract_response_text()`, `extract_actions_from_response()`, endpoints `/metadata`, `/run`, `/run_debug` |
| `auth_router` | Endpoints `/auth/login`, `/auth/token` |
| `prompt_router` | Endpoints `/prompt/webhook`, `/prompt/refresh`, `/prompt/current`, `_verify_langfuse_signature()` |
| `system_router` | Endpoints `/health`, `/metrics`, `/profiling`, `/` |

---

## Passo 10: Reescrever `app/main.py`

Após extrair rotas e middlewares, o `main.py` fica com ~175 linhas:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware import JWTAuthMiddleware, RequestIDMiddleware, SecurityHeadersMiddleware
from app.observability import get_langfuse, setup_logging, setup_tracing, shutdown_langfuse, shutdown_tracing
from app.routes import agentbench_router, auth_router, prompt_router, system_router
from app.storage import close_redis, get_redis

setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_tracing(app)
    get_langfuse()
    await get_redis()
    # ... load prompt
    yield
    # Shutdown
    await shutdown_consolidation(timeout=5.0)
    shutdown_tracing()
    await close_redis()
    shutdown_langfuse()

app = FastAPI(title=settings.MODULE_DESCRIPTION, version=settings.MODULE_VERSION, lifespan=lifespan)

app.include_router(agentbench_router)
app.include_router(auth_router)
app.include_router(prompt_router)
app.include_router(system_router)

app.add_middleware(RequestIDMiddleware)
# ... metrics, rate limit, JWT, security headers, CORS
```

---

## Passo 11: Atualizar `app/config.py`

### Novas configurações (adicionar)

```python
# Memory Consolidation (LLM-driven)
MEMORY_CONSOLIDATION_ENABLED: bool = True
MEMORY_WINDOW: int = 20
MEMORY_CONSOLIDATION_MODEL: str = ''  # vazio = usa DEFAULT_MODEL
MEMORY_CONSOLIDATION_MAX_TOKENS: int = 2048
TOOL_OUTPUT_MAX_CHARS: int = 2000
```

### Configurações mantidas (sem alteração)

Todas as seções de Auth, Model, Storage, Observability, Rate Limiting, Resilience e Server permanecem idênticas.

---

## Passo 12: Atualizar Testes

### Imports nos testes

```python
# ANTES
from agno.tools import tool
from agno.run import RunContext
from agno.exceptions import RetryAgentRun

# DEPOIS
from app.runtime import tool, RunContext, RetryAgentRun
```

### Mock do agente

```python
# ANTES — Mock do Agno Agent
with patch('app.agent.create_agent') as mock_agent:
    mock_agent.return_value.run = AsyncMock(return_value=mock_response)

# DEPOIS — Mock do litellm
with patch('litellm.acompletion') as mock_llm:
    mock_llm.return_value = mock_response
```

---

## Passo 13: Arquivos para Deletar

Após completar a migração, remova os arquivos que foram consolidados:

```bash
# Consolidados em observability.py
rm app/logging_config.py
rm app/tracing.py
rm app/langfuse_client.py

# Consolidado em middleware.py
rm app/security.py

# Se agrupou tools por domínio
rm app/tools/agendar_consulta.py
rm app/tools/cancelar_consulta.py
rm app/tools/verificar_disponibilidade.py
rm app/tools/buscar_paciente.py
rm app/tools/consultar_historico.py
rm app/tools/verificar_cliente.py
rm app/tools/consultar_convenios.py
rm app/tools/listar_servicos.py
rm app/tools/calcular_orcamento.py
rm app/tools/obter_data_hora.py
rm app/tools/salvar_dados_cliente.py
rm app/tools/salvar_preferencias.py
rm app/tools/ver_contexto_sessao.py
```

---

## Passo 14: Verificar Migração

Execute estes comandos para validar:

```bash
# 1. Imports dos novos módulos
uv run python -c "from app.runtime import tool, RunContext, RetryAgentRun, ToolRegistry; print('runtime OK')"
uv run python -c "from app.observability import setup_logging, setup_tracing, get_langfuse; print('observability OK')"
uv run python -c "from app.middleware import RequestIDMiddleware, JWTAuthMiddleware, SecurityHeadersMiddleware; print('middleware OK')"
uv run python -c "from app.agent import run_agent_loop, AgentResponse, get_litellm_model; print('agent OK')"
uv run python -c "from app.tools import agendar_consulta, buscar_paciente, listar_servicos; print('tools OK')"
uv run python -c "from app.routes import agentbench_router, auth_router, prompt_router, system_router; print('routes OK')"

# 2. Nenhum import antigo do Agno sobreviveu
grep -r "from agno\|import agno" app/

# 3. Nenhum import de arquivo deletado
grep -r "from app.logging_config\|from app.tracing\|from app.langfuse_client\|from app.security" app/

# 4. Servidor sobe
uv run uvicorn app.main:app --reload

# 5. Testes passam
uv run pytest
```

---

## Checklist de Migração

```
[ ] Atualizar pyproject.toml (remover agno, adicionar litellm + json-repair)
[ ] uv sync
[ ] Copiar app/runtime.py
[ ] Atualizar imports nas tools (agno.* → app.runtime)
[ ] (Opcional) Agrupar tools por domínio
[ ] Atualizar app/tools/__init__.py
[ ] Reescrever app/agent.py (create_agent → get_litellm_model + get_tools_registry + run_agent_loop)
[ ] Criar app/middleware.py (RequestID + JWT + SecurityHeaders)
[ ] Criar app/observability.py (logging + tracing + langfuse)
[ ] Copiar app/memory.py (novo sistema de consolidação)
[ ] Criar app/routes/ (extrair rotas do main.py)
[ ] Reescrever app/main.py (slim ~175 linhas)
[ ] Atualizar app/config.py (novas settings de memória)
[ ] Atualizar testes (imports + mocks)
[ ] Deletar arquivos obsoletos
[ ] Verificar: nenhum import agno.* restante
[ ] Verificar: servidor sobe sem erros
[ ] Verificar: testes passam
[ ] Atualizar CLAUDE.md
```

---

## FAQ

### O contrato AgentBench mudou?

Nao. Os endpoints `/metadata`, `/run`, `/run_debug` mantm a mesma interface. Clientes que consomem a API nao precisam de nenhuma alteracao.

### Tools existentes quebram?

Nao. A unica mudanca eh a linha de import (`agno.*` → `app.runtime`). A assinatura das funcoes, uso de `RunContext`, `RetryAgentRun` e retorno `str` permanecem identicos.

### Posso usar tools sync e async?

Sim. O `ToolRegistry.execute()` suporta ambos — se a funcao retornar um awaitable, ele faz `await` automaticamente.

### O session_state funciona igual?

Sim. `run_context.session_state` eh um `dict` identico ao da v1. Tools que salvam dados via `run_context.session_state['chave'] = valor` funcionam sem alteracao.

### Perco funcionalidades do Agno?

- **`enable_user_memories`**: Substituido pela consolidacao LLM-driven em `app/memory.py`, que eh mais transparente e customizavel.
- **`enable_session_summaries`**: Substituido pela consolidacao que gera fatos estruturados.
- **Knowledge Bases / RAG do Agno**: Nao tem equivalente direto na v2. Se voce usava, precisara implementar separadamente.
- **Multi-Agent Teams**: Nao tem equivalente na v2. Se usava, mantenha a v1 para esses casos.
- **AgentOS runtime features (HITL, RBAC, MCP Server)**: Substituidos por implementacoes customizadas (JWT auth, middleware customizado).

### Posso migrar incrementalmente?

Nao. A remocao do `agno` impacta todas as tools e o agent loop simultaneamente. A migracao deve ser feita de uma vez ("big bang"). Recomendamos:

1. Criar branch de migracao
2. Aplicar todos os passos
3. Rodar testes
4. Merge quando tudo estiver verde

### Muda algo no Docker/deploy?

O `Dockerfile` e `docker-compose.yml` nao precisam de alteracao. A unica mudanca eh nas dependencias Python, que sao resolvidas pelo `uv sync` durante o build.

### PostgreSQL ainda eh necessario?

O PostgreSQL era usado pelo Agno para user memories e session summaries. Na v2, **toda a memoria usa Redis**, entao PostgreSQL se torna opcional. Mantenha-o apenas se sua aplicacao usa diretamente para outros fins.
