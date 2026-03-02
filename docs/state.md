# State Management (Gerenciamento de Estado)

O sistema de gerenciamento de estado utiliza Redis para persistir dados da sessao e historico de mensagens, com fallback em memoria para quando o Redis estiver indisponivel. O estado e acessado e modificado pelas tools do agente via `RunContext`, e injetado no system prompt para garantir que o agente nunca esqueca dados importantes.

Implementacao: `app/storage.py` (persistencia), `app/runtime.py` (RunContext), `app/tools/formatar_contexto.py` (injecao no prompt)

---

## Conceitos

| Conceito | Descricao |
|----------|-----------|
| **RunContext** | Dataclass de `app/runtime.py` com `session_state`, `session_id`, `user_id` — passado para tools |
| **session_state** | Dicionario mutavel armazenado no Redis, acessivel via `run_context.session_state` |
| **Historico de mensagens** | Lista de mensagens (role + content) armazenada no Redis por conversa |
| **Injecao de contexto** | `formatar_contexto_completo()` gera texto com dados da sessao para o system prompt |
| **Redis** | Backend principal de persistencia, com fallback in-memory |

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                   SYSTEM PROMPT                          │
│  instructions + memoria de longo prazo + contexto sessao │
├─────────────────────────────────────────────────────────┤
│             HISTORICO (ultimas N mensagens)               │
│             (Redis: session:{cid}:history)                │
├─────────────────────────────────────────────────────────┤
│              SESSION STATE (Redis: session:{cid}:state)  │
│  • cliente: {nome, convenio, telefone, cpf, email, ...}  │
│  • preferencias: {horario_preferido, dentista, ...}      │
│  • agendamentos: [...]                                   │
└─────────────────────────────────────────────────────────┘
```

---

## RunContext (`app/runtime.py`)

O `RunContext` e um dataclass criado a cada execucao do agente e passado automaticamente para as tools que o solicitam:

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class RunContext:
    """Contexto passado para tools durante a execucao do agente."""
    session_state: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    user_id: str | None = None
```

O `RunContext` e criado em `execute_agent()` no `main.py`:

```python
run_context = RunContext(
    session_state=session_state,     # carregado do Redis
    session_id=conversation_id,
    user_id=conversation_id,
)
```

As tools acessam e modificam `run_context.session_state` diretamente. Apos a execucao do agente, o state atualizado e salvo de volta no Redis.

---

## Persistencia no Redis (`app/storage.py`)

### Chaves Redis

| Chave | Tipo | Descricao |
|-------|------|-----------|
| `session:{cid}:state` | String (JSON) | Estado da sessao (dicionario serializado) |
| `session:{cid}:history` | List (JSON) | Historico de mensagens da conversa |

### Funcoes de Session State

```python
from app.storage import get_session_state, set_session_state, update_session_state, delete_session_state

# Carregar estado da sessao
state = await get_session_state(conversation_id)
# Retorna {} se nao existir

# Salvar estado completo
await set_session_state(conversation_id, {"cliente": {"nome": "Joao"}})

# Atualizar parcialmente (merge com existente)
await update_session_state(conversation_id, {"preferencias": {"horario": "manha"}})

# Deletar estado
await delete_session_state(conversation_id)
```

### Funcoes de Historico de Mensagens

```python
from app.storage import add_message_to_history, get_message_history, clear_message_history

# Adicionar mensagem ao historico
await add_message_to_history(conversation_id, role="user", content="Ola!")
await add_message_to_history(conversation_id, role="assistant", content="Ola! Como posso ajudar?")

# Obter historico (limitado automaticamente)
history = await get_message_history(conversation_id, limit=40)
# Retorna: [{"role": "user", "content": "...", "metadata": {}}, ...]

# Limpar historico
await clear_message_history(conversation_id)
```

O tamanho maximo do historico e controlado automaticamente:
- Com consolidacao habilitada: `MEMORY_WINDOW * 2` mensagens
- Sem consolidacao: `NUM_HISTORY_RUNS * 2` mensagens

### Fallback In-Memory

Se o Redis estiver indisponivel, todas as operacoes usam dicionarios em memoria como fallback:

```python
# Fallbacks internos (automaticos, transparentes)
_memory_store: dict[str, Any] = {}        # session state
_history_store: dict[str, list] = {}       # historico
_cache_store: dict[str, Any] = {}          # cache geral
```

Isso garante que a aplicacao continue funcionando em modo degradado, porem sem persistencia entre reinicializacoes.

---

## Tools de Gerenciamento de Estado

O agente modifica o session state atraves de tools dedicadas. Cada tool recebe `run_context: RunContext` como primeiro parametro.

### `salvar_dados_cliente` (`app/tools/salvar_dados_cliente.py`)

Persiste dados cadastrais do paciente na sessao. Campos vazios nao sobrescrevem dados existentes.

```python
from app.runtime import RunContext, tool

@tool
def salvar_dados_cliente(
    run_context: RunContext,
    nome: str,
    paciente_id: str = "",
    telefone: str = "",
    email: str = "",
    convenio: str = "",
    cpf: str = "",
) -> str:
    """Salva ou atualiza os dados cadastrais do cliente da sessao atual."""
    state = run_context.session_state
    if "cliente" not in state:
        state["cliente"] = {}

    if nome:
        state["cliente"]["nome"] = nome
    if convenio:
        state["cliente"]["convenio"] = convenio
    # ... demais campos

    return "Dados do cliente salvos: ..."
```

### `salvar_preferencias` (`app/tools/salvar_preferencias.py`)

Salva preferencias ou anotacoes temporarias do paciente (horarios, dentista preferido, alergias, etc.).

```python
@tool
def salvar_preferencias(
    run_context: RunContext,
    chave: str,
    valor: str,
) -> str:
    """Salva uma preferencia ou anotacao temporaria do paciente."""
    state = run_context.session_state
    if "preferencias" not in state:
        state["preferencias"] = {}

    state["preferencias"][chave] = {
        "valor": valor,
        "salvo_em": datetime.now().isoformat(),
    }
    return f"Preferencia salva: {chave} = {valor}"
```

### `ver_contexto_sessao` (`app/tools/ver_contexto_sessao.py`)

Recupera todos os dados e preferencias salvos na sessao atual. Util para o agente relembrar informacoes coletadas anteriormente.

```python
@tool
def ver_contexto_sessao(run_context: RunContext) -> str:
    """Recupera todos os dados do cliente e preferencias salvos nesta sessao."""
    state = run_context.session_state
    # Formata cliente, preferencias e agendamentos
    return resumo_formatado
```

---

## Injecao de Contexto no Prompt

### O Problema

Quando o historico de mensagens e limitado (ex: `NUM_HISTORY_RUNS=2`), o agente "esquece" dados informados nas primeiras mensagens. Nome do paciente, convenio e preferencias se perdem apos poucos turnos.

### A Solucao: Session State + Injecao no System Prompt

O `formatar_contexto_completo()` (em `app/tools/formatar_contexto.py`) combina a memoria de longo prazo e o session state em um bloco de texto que e injetado no system prompt:

```python
def formatar_contexto_completo(session_state: dict, memory_context: str = "") -> str:
    """Combina memoria consolidada + estado da sessao para injecao no prompt."""
    parts = []

    if memory_context:
        parts.append(
            "\n\n--- MEMORIA DE LONGO PRAZO ---\n"
            + memory_context
            + "\n--- FIM DA MEMORIA ---"
        )

    state_context = formatar_contexto_state(session_state)
    if state_context:
        parts.append(state_context)

    return "".join(parts)
```

O `formatar_contexto_state()` gera o bloco de sessao:

```
--- CONTEXTO DA SESSAO (dados ja coletados, NAO pergunte novamente) ---
DADOS DO CLIENTE ATUAL: nome: Joao Pereira | convenio: OdontoPrev | telefone: (11) 98765-4321
PREFERENCIAS DO CLIENTE: horario_preferido: manha | dentista_preferido: Dra. Maria
AGENDAMENTOS ATIVOS: CON-ABC123 - Limpeza em 2025-02-10 as 09:00 com Dra. Maria Silva
--- FIM DO CONTEXTO ---
```

### Fluxo em `execute_agent()` (`app/main.py`)

```python
async def execute_agent(request, debug=False):
    # 1. Carregar session state do Redis
    session_state = await get_session_state(conversation_id)

    # 2. Obter memoria consolidada
    memory_context = await get_memory_context(conversation_id)

    # 3. Formatar contexto completo
    full_context = formatar_contexto_completo(session_state, memory_context)

    # 4. Compilar prompt com contexto injetado
    instructions = compile_prompt(template, session_context=full_context)

    # 5. Criar RunContext com state carregado
    run_context = RunContext(
        session_state=session_state,
        session_id=conversation_id,
        user_id=conversation_id,
    )

    # 6. Executar agent loop (tools podem modificar session_state)
    response = await run_agent_loop(messages, tools, run_context, model)

    # 7. Persistir state atualizado de volta no Redis
    if response.session_state:
        await update_session_state(conversation_id, response.session_state)
```

---

## Estrutura do Session State

O session state segue uma estrutura convencional:

```python
{
    "cliente": {
        "nome": "Joao Pereira",
        "paciente_id": "PAC001",
        "telefone": "(11) 98765-4321",
        "email": "joao@email.com",
        "convenio": "OdontoPrev",
        "cpf": "123.456.789-00",
        "atualizado_em": "2025-02-10T14:30:00"
    },
    "preferencias": {
        "horario_preferido": {
            "valor": "manha",
            "salvo_em": "2025-02-10T14:31:00"
        },
        "dentista_preferido": {
            "valor": "Dra. Maria Silva",
            "salvo_em": "2025-02-10T14:32:00"
        },
        "alergias": {
            "valor": "latex",
            "salvo_em": "2025-02-10T14:33:00"
        }
    },
    "agendamentos": [
        {
            "id": "CON-ABC123",
            "servico_nome": "Limpeza",
            "data": "2025-02-15",
            "horario": "09:00",
            "dentista_nome": "Dra. Maria Silva",
            "status": "confirmado"
        }
    ]
}
```

---

## Decorator `@tool` e ToolRegistry (`app/runtime.py`)

### `@tool`

Converte uma funcao Python em um `ToolDefinition` compativel com a API de tool-calling do LiteLLM/OpenAI. O parametro `run_context` e filtrado do JSON Schema (injetado automaticamente pelo registry na execucao).

```python
from app.runtime import tool, RunContext

@tool
def minha_tool(run_context: RunContext, parametro: str) -> str:
    """Descricao que o LLM vera."""
    run_context.session_state["chave"] = parametro
    return "Resultado"
```

### `ToolRegistry`

Registra todas as tools e executa chamadas:

```python
registry = ToolRegistry()
registry.register(salvar_dados_cliente)
registry.register(salvar_preferencias)
registry.register(ver_contexto_sessao)

# Gera definicoes para litellm
tool_definitions = registry.get_definitions()

# Executa tool com injecao de RunContext
result = await registry.execute("salvar_dados_cliente", args, run_context)
```

---

## Quando Usar Cada Tipo de Dado

| Tipo | Onde Armazenar | Duracao | Exemplo |
|------|---------------|---------|---------|
| **Dados cadastrais** | `session_state["cliente"]` via `salvar_dados_cliente` | Toda a sessao | Nome, CPF, convenio, telefone |
| **Preferencias** | `session_state["preferencias"]` via `salvar_preferencias` | Toda a sessao | Horario preferido, dentista, alergias |
| **Dados operacionais** | `session_state["agendamentos"]` via tool especifica | Toda a sessao | Consultas agendadas/canceladas |
| **Fatos de longo prazo** | `memory:{cid}:facts` via consolidacao LLM | Entre sessoes (TTL) | Historico resumido, perfil do paciente |
| **Contexto conversacional** | `session:{cid}:history` (automatico) | Ultimas N mensagens | O que foi dito recentemente |

---

## Instrucoes para o LLM

O prompt do agente DEVE incluir instrucoes de gestao de memoria para que o LLM saiba quando usar as tools:

```
GESTAO DE MEMORIA (CRITICO):
- SEMPRE use salvar_dados_cliente quando o paciente informar nome, telefone, e-mail, CPF ou convenio
- SEMPRE use salvar_preferencias quando o paciente mencionar horarios preferidos, dentista preferido,
  alergias, medos ou qualquer observacao relevante
- Use ver_contexto_sessao se precisar relembrar dados ja coletados
- Se o CONTEXTO DA SESSAO estiver presente nas instrucoes, use esses dados e NAO pergunte novamente
- Ao agendar, use os dados do cliente ja salvos no contexto da sessao
```

Essas instrucoes ja estao no `AGENT_INSTRUCTIONS_FALLBACK` em `app/config.py`.

---

## Configuracao

```bash
# Historico de mensagens (sem consolidacao)
NUM_HISTORY_RUNS=2

# Consolidacao de memoria (complementa o session state)
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_WINDOW=20

# TTL do Redis (em segundos)
REDIS_SESSION_TTL=86400

# Redis connection pool
REDIS_URL=redis://localhost:6379/0
REDIS_POOL_MAX_SIZE=20
REDIS_CONNECT_TIMEOUT=2.0
REDIS_SOCKET_TIMEOUT=5.0
```

---

## Resiliencia

| Aspecto | Comportamento |
|---------|---------------|
| **Redis indisponivel** | Fallback automatico para armazenamento in-memory (dicionarios Python) |
| **Fallback transparente** | `get_session_state()` tenta Redis, cai para `_memory_store` se falhar |
| **Sem persistencia no fallback** | Dados in-memory sao perdidos se a aplicacao reiniciar |
| **Connection pool** | Pool de conexoes configuravel (`REDIS_POOL_MAX_SIZE`) para desempenho |
| **TTL automatico** | Chaves expiram apos `REDIS_SESSION_TTL` (padrao: 24h) |
| **Estado degradado** | Endpoint `/health` reporta `degraded` quando Redis esta indisponivel |

---

## Boas Praticas

| Pratica | Descricao |
|---------|-----------|
| **Salve dados cedo** | Use `salvar_dados_cliente` assim que o paciente informar dados |
| **Use `get()` seguro** | Acesse state com `.get("chave", {})` para evitar KeyError |
| **Instrua o LLM** | O prompt DEVE dizer ao agente para usar as tools de memoria |
| **Injete contexto** | `formatar_contexto_completo` garante que dados sobrevivam ao rolloff do historico |
| **Combine com memoria** | Session state (imediato) + memoria consolidada (longo prazo) se complementam |
| **Nao persista segredos** | Nao armazene senhas, tokens ou chaves de API no session state |
| **Monitore Redis** | Use `/health` para verificar disponibilidade e `/profiling` para performance |
