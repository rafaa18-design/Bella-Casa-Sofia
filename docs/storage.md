# Storage, Estado e Memoria

Este documento cobre o sistema de armazenamento baseado em Redis: session state, historico de mensagens, cache e degradacao graciosa.

---

## Visao Geral da Arquitetura

O storage utiliza **Redis** como backend unico para estado de sessao, historico de mensagens e cache. Nao ha dependencia de PostgreSQL para o funcionamento do agente. Quando o Redis esta indisponivel, o sistema degrada graciosamente para armazenamento em memoria.

| Camada | Backend | Chave Redis | TTL |
|--------|---------|-------------|-----|
| Session State | Redis (+ fallback em memoria) | `session:{cid}:state` | `REDIS_SESSION_TTL` (24h) |
| Historico de Mensagens | Redis (+ fallback em memoria) | `session:{cid}:history` | `REDIS_SESSION_TTL` (24h) |
| Cache | Redis (+ fallback em memoria) | `cache:{key}` | `REDIS_CACHE_TTL` (1h) |
| Memoria Consolidada | Redis | `memory:{cid}:facts` | Sem expiracao |

---

## Conexao Redis

### Configuracao

```bash
# .env
REDIS_URL=redis://localhost:6379/0
REDIS_SESSION_TTL=86400          # TTL de sessao em segundos (padrao: 24h)
REDIS_CACHE_TTL=3600             # TTL de cache em segundos (padrao: 1h)

# Connection Pool
REDIS_POOL_MIN_SIZE=5            # Conexoes minimas no pool
REDIS_POOL_MAX_SIZE=20           # Conexoes maximas no pool
REDIS_CONNECT_TIMEOUT=2.0        # Timeout de conexao (segundos)
REDIS_SOCKET_TIMEOUT=5.0         # Timeout de operacao (segundos)
```

### Obtendo o Cliente

```python
# app/storage.py

from app.storage import get_redis

client = await get_redis()
# Retorna aioredis.Redis ou None (se Redis indisponivel)
```

O cliente e criado uma unica vez (singleton) com connection pooling. Se a conexao falhar, `get_redis()` retorna `None` e todas as operacoes degradam para armazenamento em memoria.

### Estatisticas do Pool

```python
from app.storage import get_redis_pool_stats

stats = await get_redis_pool_stats()
# {'max_connections': 20, 'current_connections': 3, 'available_connections': 17}
```

---

## Session State

O session state armazena dados estruturados da conversa (dados do cliente, preferencias, carrinho, etc.). E persistido no Redis com TTL configuravel e automaticamente injetado no system prompt do agente.

### Funcoes Disponiveis

| Funcao | Descricao |
|--------|-----------|
| `get_session_state(cid)` | Retorna o estado atual (dict) |
| `set_session_state(cid, state, ttl)` | Define o estado completo |
| `update_session_state(cid, updates)` | Merge com estado existente |
| `delete_session_state(cid)` | Remove estado do Redis e memoria |

### Exemplo de Uso

```python
from app.storage import get_session_state, update_session_state, delete_session_state

# Ler estado
estado = await get_session_state("conv_123")
# {}  (vazio se nao existir)

# Atualizar (merge)
await update_session_state("conv_123", {
    "nome_cliente": "Joao",
    "convenio": "OdontoPrev",
})

# Ler novamente
estado = await get_session_state("conv_123")
# {"nome_cliente": "Joao", "convenio": "OdontoPrev"}

# Deletar
await delete_session_state("conv_123")
```

### Acessando em uma Tool

As tools acessam o session state via `RunContext`, que e injetado automaticamente pelo agent loop:

```python
from app.runtime import tool, RunContext

@tool
def salvar_dados_cliente(
    run_context: RunContext,
    nome: str,
    convenio: str = "",
) -> str:
    """Salva dados do cliente no contexto da sessao."""
    run_context.session_state["nome_cliente"] = nome
    if convenio:
        run_context.session_state["convenio"] = convenio
    return f"Dados salvos: {nome}"
```

O `session_state` do `RunContext` e sincronizado com o Redis ao final de cada turno pelo agent loop.

---

## Historico de Mensagens

O historico armazena as mensagens trocadas entre usuario e agente. A quantidade de mensagens mantidas depende da configuracao de memoria:

- **Com consolidacao habilitada**: `MEMORY_WINDOW * 2` mensagens
- **Sem consolidacao**: `NUM_HISTORY_RUNS * 2` mensagens

### Funcoes Disponiveis

| Funcao | Descricao |
|--------|-----------|
| `add_message_to_history(cid, role, content, metadata)` | Adiciona mensagem |
| `get_message_history(cid, limit)` | Retorna historico (mais recentes) |
| `clear_message_history(cid)` | Limpa todo o historico |

### Exemplo de Uso

```python
from app.storage import add_message_to_history, get_message_history, clear_message_history

# Adicionar mensagens
await add_message_to_history("conv_123", role="user", content="Ola!")
await add_message_to_history("conv_123", role="assistant", content="Ola! Como posso ajudar?")

# Recuperar historico
mensagens = await get_message_history("conv_123")
# [
#   {"role": "user", "content": "Ola!", "metadata": {}},
#   {"role": "assistant", "content": "Ola! Como posso ajudar?", "metadata": {}},
# ]

# Com limite explicito
ultimas = await get_message_history("conv_123", limit=10)

# Limpar
await clear_message_history("conv_123")
```

### Trim Automatico

Mensagens sao automaticamente aparadas para respeitar o limite configurado. No Redis, isso e feito com `LTRIM`; no fallback em memoria, com fatiamento da lista.

```python
# Com MEMORY_CONSOLIDATION_ENABLED=true e MEMORY_WINDOW=20:
# max_messages = 20 * 2 = 40 mensagens mantidas

# Sem consolidacao, com NUM_HISTORY_RUNS=2:
# max_messages = 2 * 2 = 4 mensagens mantidas
```

---

## Cache

Operacoes genericas de cache com TTL configuravel.

```python
from app.storage import cache_get, cache_set, cache_delete

# Armazenar
await cache_set("horarios_disponiveis", {"seg": ["09:00", "10:00"]}, ttl=600)

# Recuperar
dados = await cache_get("horarios_disponiveis")

# Remover
await cache_delete("horarios_disponiveis")
```

As chaves de cache sao prefixadas automaticamente com `cache:` no Redis.

---

## Degradacao Graciosa

Quando o Redis esta indisponivel, todas as operacoes continuam funcionando usando dicionarios em memoria. Isso permite que o agente opere mesmo sem Redis, com as seguintes limitacoes:

| Aspecto | Com Redis | Sem Redis (fallback) |
|---------|-----------|----------------------|
| Persistencia | Sim (sobrevive a restart) | Nao (perdido no restart) |
| Compartilhamento | Entre instancias | Apenas local |
| TTL | Automatico | Sem expiracao |
| Performance | Alta (connection pool) | Alta (memoria local) |

### Verificando Disponibilidade

```python
from app.storage import is_redis_available

if is_redis_available():
    print("Redis conectado")
else:
    print("Operando em modo degradado (in-memory)")
```

---

## Memoria Consolidada

O sistema de consolidacao de memoria (`app/memory.py`) utiliza Redis para armazenar fatos de longo prazo extraidos do historico de conversas por um LLM.

### Chaves Redis

| Chave | Tipo | Descricao |
|-------|------|-----------|
| `memory:{cid}:facts` | String | Fatos consolidados (markdown) |
| `memory:{cid}:log` | List | Log de entradas para busca |
| `memory:{cid}:unconsolidated` | String | Contador de mensagens nao consolidadas |
| `memory:{cid}:last_consolidated` | String | Indice da ultima mensagem consolidada |

### Configuracao

```bash
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_WINDOW=20                              # Mensagens antes de consolidar
MEMORY_CONSOLIDATION_MODEL=claude-haiku-4-5-20251001  # Modelo para consolidacao
MEMORY_CONSOLIDATION_MAX_TOKENS=1024
```

O fluxo funciona assim:
1. A cada mensagem, o contador `unconsolidated` e incrementado
2. Quando `unconsolidated >= MEMORY_WINDOW`, a consolidacao e disparada em background
3. Um LLM (configuravel, geralmente barato) analisa o historico e extrai fatos estruturados
4. Os fatos sao armazenados no Redis e injetados no system prompt nas proximas interacoes

---

## Variaveis de Ambiente (Resumo)

| Variavel | Descricao | Padrao |
|----------|-----------|--------|
| `REDIS_URL` | URL de conexao Redis | `redis://localhost:6379/0` |
| `REDIS_SESSION_TTL` | TTL de sessao (segundos) | `86400` (24h) |
| `REDIS_CACHE_TTL` | TTL de cache (segundos) | `3600` (1h) |
| `REDIS_POOL_MIN_SIZE` | Conexoes minimas no pool | `5` |
| `REDIS_POOL_MAX_SIZE` | Conexoes maximas no pool | `20` |
| `REDIS_CONNECT_TIMEOUT` | Timeout de conexao (segundos) | `2.0` |
| `REDIS_SOCKET_TIMEOUT` | Timeout de socket (segundos) | `5.0` |
| `MEMORY_CONSOLIDATION_ENABLED` | Habilitar consolidacao de memoria | `true` |
| `MEMORY_WINDOW` | Mensagens antes de consolidar | `20` |
| `MEMORY_CONSOLIDATION_MODEL` | Modelo para consolidacao | (usa `DEFAULT_MODEL`) |
| `MEMORY_CONSOLIDATION_MAX_TOKENS` | Tokens maximos na consolidacao | `1024` |
| `NUM_HISTORY_RUNS` | Historico sem consolidacao | `2` |

---

## Referencia da API (`app/storage.py`)

```python
# Redis Client
async def get_redis() -> aioredis.Redis | None
async def close_redis() -> None
def is_redis_available() -> bool
async def get_redis_pool_stats() -> dict[str, int] | None

# Session State
async def get_session_state(conversation_id: str) -> dict[str, Any]
async def set_session_state(conversation_id: str, state: dict, ttl: int | None = None)
async def update_session_state(conversation_id: str, updates: dict)
async def delete_session_state(conversation_id: str)

# Message History
async def add_message_to_history(conversation_id: str, role: str, content: str, metadata: dict | None = None)
async def get_message_history(conversation_id: str, limit: int | None = None) -> list[dict]
async def clear_message_history(conversation_id: str)

# Cache
async def cache_get(key: str) -> Any | None
async def cache_set(key: str, value: Any, ttl: int | None = None)
async def cache_delete(key: str)
```
