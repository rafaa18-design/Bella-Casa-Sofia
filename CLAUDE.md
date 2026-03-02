# Asani AI Agent Template

Template de módulo de agente de IA seguindo o padrão **AgentBench** (contrato interno Asani) com **LiteLLM** + agent loop próprio.

## Visão Geral

Este template implementa um módulo de IA compatível com:

- **AgentBench Standard**: Endpoints `/metadata`, `/run`, `/run_debug`
- **LiteLLM**: Abstração multi-provider para chamadas LLM (Anthropic, OpenAI, Vertex AI)
- **Agent Loop Próprio**: Loop iterativo de tool-calling sem framework externo
- **Memória Consolidada**: Sistema LLM-driven de consolidação de memória de longo prazo
- **Autenticação JWT**: Middleware customizado com rotas excluídas configuráveis
- **Multi-Provider**: Suporte a Anthropic, OpenAI e Vertex AI via litellm

### Princípios Chave

| Princípio | Descrição |
|-----------|-----------|
| **Soberania do Módulo** | O módulo é o orquestrador absoluto do seu pipeline interno |
| **Observabilidade** | AgentBench é o observador soberano do comportamento |
| **Estado Gerenciado** | O módulo gerencia seu próprio estado, histórico e contexto |
| **Trajetória Completa** | AgentBench apenas chama endpoints e recebe trajetórias completas |

## Estrutura do Projeto

```
asani-ai-agent-template/
├── app/
│   ├── main.py              # FastAPI app, lifespan, middleware/router registration (~150 linhas)
│   ├── agent.py             # Utilitários litellm + agent loop iterativo
│   ├── runtime.py           # RunContext, @tool decorator, ToolRegistry, exceptions
│   ├── middleware.py         # RequestID, JWT auth e security headers middlewares
│   ├── observability.py     # Logging estruturado, OpenTelemetry tracing, Langfuse client
│   ├── memory.py            # Consolidação LLM-driven de memória
│   ├── auth.py              # Autenticação JWT + bcrypt
│   ├── audit.py             # Audit logging para operações sensíveis
│   ├── models.py            # Schemas Pydantic
│   ├── storage.py           # Redis (session state, histórico, cache)
│   ├── config.py            # Settings
│   ├── metrics.py           # Métricas Prometheus
│   ├── profiling.py         # Async profiling utilities
│   ├── rate_limiter.py      # Rate limiting (Redis/in-memory)
│   ├── resilience.py        # Circuit breaker + retry
│   ├── prompt_manager.py    # Gestão de prompts (Langfuse)
│   ├── routes/              # Endpoints organizados por domínio
│   │   ├── __init__.py
│   │   ├── agentbench.py    # /metadata, /run, /run_debug
│   │   ├── auth.py          # /auth/login, /auth/token
│   │   ├── prompts.py       # /prompt/webhook, /prompt/refresh, /prompt/current
│   │   └── system.py        # /health, /metrics, /profiling, /
│   └── tools/               # Ferramentas agrupadas por domínio
│       ├── __init__.py
│       ├── _helpers.py
│       ├── _mock_data.py
│       ├── consultas.py     # agendar, cancelar, verificar disponibilidade
│       ├── pacientes.py     # buscar, histórico, verificar cliente, convênios
│       ├── catalogo.py      # listar serviços, calcular orçamento, obter data/hora
│       ├── sessao.py        # salvar dados, salvar preferências, ver contexto
│       └── formatar_contexto.py  # Formatador de contexto (não é tool)
├── scripts/
│   └── hash_password.py     # CLI para gerar hashes bcrypt
├── docs/                    # Documentação detalhada
├── tests/                   # Testes unitários
└── CLAUDE.md                # Este arquivo
```

## Arquitetura do Agent Loop

```
Request → parse_multimodal_input()
       → build_system_messages(instructions, text, images, history)
       → run_agent_loop(messages, tools, run_context, model)
           ├── litellm.acompletion() → tool_calls?
           │   ├── Yes → ToolRegistry.execute() → add tool results → repeat
           │   └── No  → return AgentResponse(content, tokens, tools_used)
           ├── RetryAgentRun → feedback como tool result, continua loop
           └── StopAgentRun → para loop imediatamente
       → Memory consolidation (background, se MEMORY_WINDOW atingido)
       → Return RunResponse
```

## Comandos Rápidos

```bash
uv sync                                  # Instalar dependências
uv run uvicorn app.main:app --reload     # Servidor dev
uv run pytest                            # Testes
uv run pytest --cov=app --cov-report=term-missing  # Testes com cobertura
uv run scripts/hash_password.py          # Gerar hash bcrypt
make dev                                 # Docker dev
```

## Guia Rápido por Tarefa

### Criar uma nova ferramenta (tool)

Tools são agrupadas por domínio em arquivos dentro de `app/tools/`. Adicione ao arquivo de domínio adequado ou crie um novo se necessário:

1. Adicione a tool ao arquivo de domínio (ex: `app/tools/consultas.py`):

```python
"""Tool: minha_tool — Descrição breve."""
from app.runtime import tool, RetryAgentRun

@tool
def minha_tool(parametro: str) -> str:
    """Descrição para o LLM."""
    if not valido(parametro):
        raise RetryAgentRun("Feedback para o modelo corrigir")
    return resultado
```

Se precisar de acesso ao estado da sessão, use `RunContext`:

```python
from app.runtime import tool, RunContext

@tool
def minha_tool(run_context: RunContext, dados: str) -> str:
    """Tool que acessa session state."""
    run_context.session_state['chave'] = dados
    return "Dados salvos"
```

2. Registre em `app/tools/__init__.py` (re-export) e em `app/agent.py` na lista dentro de `get_tools_registry()`.

> **Dados mockados (`_mock_data.py`) são APENAS para desenvolvimento.**
> Em produção, substitua por integrações reais (APIs, banco de dados, serviços externos).

### Modificar configuração do agente

Edite `app/agent.py`:

```python
# Modelo litellm (multi-provider)
def get_litellm_model(model_id: str) -> str:
    # Retorna "anthropic/claude-...", "openai/gpt-...", "vertex_ai/..."

# Registro de tools
def get_tools_registry() -> ToolRegistry:
    # Adicione/remova tools aqui

# Construção de messages
def build_system_messages(instructions, text, images, history) -> list[dict]:
    # System prompt + conversation history + user message
```

### Gerenciar memória de longo prazo

O sistema usa **consolidação LLM-driven** (arquivo `app/memory.py`):

1. A cada mensagem, incrementa um contador `unconsolidated`
2. Quando `unconsolidated >= MEMORY_WINDOW`, um LLM mais barato consolida o histórico em fatos estruturados
3. Fatos são armazenados no Redis (`memory:{cid}:facts`) e injetados no system prompt

Configuração via `.env`:
```bash
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_WINDOW=20
MEMORY_CONSOLIDATION_MODEL=claude-haiku-4-5-20251001  # Modelo barato
MEMORY_CONSOLIDATION_MAX_TOKENS=1024
```

### Gerenciar dados da sessão (contexto pequeno)

**Problema**: O agente pode esquecer dados de turnos anteriores.

**Solução**: Tools de memória salvam dados no `session_state`, que é injetado no system prompt:

```python
# Tools disponíveis:
salvar_dados_cliente(run_context, nome="João", convenio="OdontoPrev")
salvar_preferencias(run_context, chave="horario_preferido", valor="manhã")
ver_contexto_sessao(run_context)
```

O contexto é automaticamente formatado e injetado via `formatar_contexto_completo()`.

### Adicionar novo endpoint

Edite `app/main.py`. Siga o padrão AgentBench.

## Arquivos Importantes

| Arquivo | Propósito |
|---------|-----------|
| `app/main.py` | FastAPI app, lifespan, middleware/router registration |
| `app/agent.py` | Utilitários litellm + agent loop iterativo com tool-calling |
| `app/runtime.py` | RunContext, @tool, ToolRegistry, RetryAgentRun, StopAgentRun |
| `app/middleware.py` | RequestID, JWT auth e security headers middlewares |
| `app/observability.py` | Logging estruturado, OpenTelemetry tracing, Langfuse client |
| `app/memory.py` | Consolidação LLM-driven de memória |
| `app/auth.py` | Autenticação JWT com bcrypt |
| `app/routes/` | Endpoints organizados: agentbench, auth, prompts, system |
| `app/tools/__init__.py` | Definição e export de ferramentas |
| `app/models.py` | Schemas Pydantic para AgentBench |
| `app/config.py` | Configurações (pydantic-settings) |
| `app/storage.py` | Redis (session state, histórico, cache) |
| `app/metrics.py` | Métricas Prometheus |
| `app/rate_limiter.py` | Rate limiting com Redis |
| `app/resilience.py` | Circuit breaker e retry |
| `scripts/hash_password.py` | CLI para bcrypt |

## Variáveis de Ambiente Essenciais

```bash
# Identidade do módulo
MODULE_ID=meu-agente
MODULE_VERSION=1.0.0

# API Keys (pelo menos uma)
ANTHROPIC_API_KEY=sk-ant-...  # ou OPENAI_API_KEY

# Storage
REDIS_URL=redis://localhost:6379/0

# Autenticação
AUTH_ENABLED=true
JWT_SECRET=chave-secreta-forte-minimo-32-chars
AUTH_USERS='{"admin": "$2b$12$..."}'  # Use bcrypt! Gerar: uv run scripts/hash_password.py

# CORS - Configure origens específicas para produção
CORS_ORIGINS='["https://app.example.com"]'

# Memória Consolidada
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_WINDOW=20
MEMORY_CONSOLIDATION_MODEL=claude-haiku-4-5-20251001

# Observabilidade
METRICS_ENABLED=true
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Resiliência
RETRY_MAX_ATTEMPTS=3
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
SHUTDOWN_TIMEOUT=30
```

## Padrões do Projeto

- **Error Handling**: Use `RetryAgentRun` para feedback ao modelo, `StopAgentRun` para parar execução (ambos em `app.runtime`)
- **Tools**: Sempre com docstrings descritivas, validação de inputs, decorator `@tool` de `app.runtime`
- **Storage**: Redis para session state, histórico e cache (com connection pooling)
- **Auth**: JWT obrigatório em todos os endpoints exceto `/health`, `/auth/login`, `/metrics`
- **Segurança**: Security headers (HSTS, CSP, X-Frame-Options), bcrypt para senhas, CORS específico
- **Observabilidade**: Métricas Prometheus, tracing OpenTelemetry, logs estruturados, audit logging

## Observabilidade

### Métricas Prometheus (`/metrics`)

```python
# Métricas disponíveis:
# - http_requests_total: Requisições por método/path/status
# - http_request_duration_seconds: Latência das requisições
# - http_requests_in_progress: Requisições em andamento
# - agent_runs_total: Execuções do agente por status
# - agent_run_duration_seconds: Duração das execuções
# - memory_consolidation_total: Consolidações por status (scheduled/completed/failed)
# - memory_consolidation_duration_seconds: Latência da consolidação
# - rate_limit_hits_total: Requisições bloqueadas por rate limit
# - circuit_breaker_state: Estado do circuit breaker (0=closed, 1=open, 2=half-open)
```

### OpenTelemetry Tracing

```python
from app.observability import setup_tracing  # Tracing setup is in observability module

async def minha_funcao():
    with create_span('operacao', {'user_id': user_id}) as span:
        result = await processar()
        span.set_attribute('result_size', len(result))
```

## API Endpoints

### AgentBench (Obrigatórios)

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/metadata` | GET | Capacidades do módulo |
| `/run` | POST | Execução em produção |
| `/run_debug` | POST | Execução com trajetória completa |

### Sistema

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/health` | GET | Health check (Redis) |
| `/metrics` | GET | Métricas Prometheus |
| `/profiling` | GET | Estatísticas de profiling async |
| `/` | GET | Informações básicas do módulo |

### Autenticação

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/auth/login` | POST | Obter token JWT (usuário/senha) |
| `/auth/token` | POST | Criar token (requer scope admin) |

### Prompts (Langfuse)

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/prompts/webhook` | POST | Webhook para atualização de prompts |
| `/prompts/refresh` | POST | Forçar atualização do prompt |
| `/prompts/current` | GET | Ver prompt atual em cache |

## Autenticação

### Gerar Hash Bcrypt

```bash
uv run scripts/hash_password.py                          # Interativo
uv run scripts/hash_password.py --password minha_senha    # Direto
uv run scripts/hash_password.py --password minha_senha --json --username admin  # JSON
uv run scripts/hash_password.py --verify '$2b$12$...' --password minha_senha    # Verificar
```

### Uso da API

```bash
# Login e obter token
curl -X POST "http://localhost:8000/auth/login?username=admin&password=minha_senha"

# Usar token
curl -H "Authorization: Bearer <token>" http://localhost:8000/metadata

# Criar token para outro usuário (requer scope admin)
curl -H "Authorization: Bearer <admin-token>" \
  -X POST "http://localhost:8000/auth/token?user_id=new_user&scopes=read,write"
```

## Graceful Shutdown

- Aguarda requisições em andamento (até SHUTDOWN_TIMEOUT segundos)
- Aguarda consolidações de memória ativas
- Fecha conexões Redis
- Flush de traces e métricas
