# State Management (Gerenciamento de Estado)

O Agno fornece um sistema robusto de gerenciamento de estado para manter dados entre execuções do agente.

---

## Conceitos

| Conceito | Descrição |
|----------|-----------|
| **session_state** | Estado mutável por sessão, acessível via `run_context.session_state` |
| **session_id** | Identificador único da sessão/conversa |
| **user_id** | Identificador do usuário (permite múltiplos usuários) |
| **db** | Backend de persistência (PostgreSQL, SQLite) |

---

## Session State Básico

```python
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat
from agno.run import RunContext


def add_item(run_context: RunContext, item: str) -> str:
    """Add an item to the shopping list."""
    run_context.session_state["shopping_list"].append(item)
    return f"Added {item}. List: {run_context.session_state['shopping_list']}"


agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    db=SqliteDb(db_file="tmp/state.db"),
    # Estado inicial padrão para todas as sessões
    session_state={"shopping_list": []},
    tools=[add_item],
    # Usar state nas instruções
    instructions="Shopping list: {shopping_list}",
    markdown=True,
)

# Executa e modifica o estado
agent.print_response("Add milk and eggs", stream=True)

# Verificar estado final
print(f"Final state: {agent.get_session_state()}")
# Output: {'shopping_list': ['milk', 'eggs']}
```

---

## State com PostgreSQL

```python
from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.openai import OpenAIChat

db_url = "postgresql+psycopg://ai:ai@localhost:5532/ai"
db = PostgresDb(db_url=db_url, session_table="sessions")

agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    instructions="User name is {user_name} and age is {age}",
    db=db,
)

# Criar sessão com estado inicial
agent.print_response(
    "What is my name?",
    session_id="user_1_session_1",
    user_id="user_1",
    session_state={"user_name": "John", "age": 30},
)

# Carregar estado existente automaticamente
agent.print_response(
    "How old am I?",
    session_id="user_1_session_1",
    user_id="user_1",
)
```

---

## Múltiplos Usuários e Sessões

```python
from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.openai import OpenAIChat

db = PostgresDb(db_url="postgresql+psycopg://...")

agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    db=db,
)

# Usuário 1, Sessão 1
agent.print_response(
    "Hello!",
    session_id="session_456",
    user_id="alice@example.com",
)

# Usuário 1, Sessão 2 (nova conversa)
agent.print_response(
    "Hi there!",
    session_id="session_789",
    user_id="alice@example.com",
)

# Usuário 2, Sessão diferente
agent.print_response(
    "Hello!",
    session_id="session_101",
    user_id="bob@example.com",
)
```

---

## Acessando State em Tools

```python
from agno.run import RunContext
from agno.tools import tool


@tool
def add_to_cart(run_context: RunContext, item: str, quantity: int = 1) -> str:
    """Add item to shopping cart."""
    cart = run_context.session_state.get("cart", [])
    cart.append({"item": item, "quantity": quantity})
    run_context.session_state["cart"] = cart
    return f"Added {quantity}x {item} to cart"


@tool
def get_cart_total(run_context: RunContext) -> str:
    """Get cart items count."""
    cart = run_context.session_state.get("cart", [])
    total = sum(item["quantity"] for item in cart)
    return f"Cart has {total} items"


@tool
def clear_cart(run_context: RunContext) -> str:
    """Clear the shopping cart."""
    run_context.session_state["cart"] = []
    return "Cart cleared"


agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    db=SqliteDb(db_file="tmp/shop.db"),
    session_state={"cart": []},
    tools=[add_to_cart, get_cart_total, clear_cart],
    instructions="Current cart: {cart}",
)
```

---

## State em Instruções

O Agno substitui variáveis do state nas instruções automaticamente:

```python
agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    db=db,
    session_state={
        "user_name": "Guest",
        "preferences": {"language": "pt-BR"},
        "cart": [],
    },
    instructions="""
    User: {user_name}
    Language preference: {preferences[language]}
    Cart items: {cart}

    Always greet the user by name.
    Respond in their preferred language.
    """,
)
```

---

## State Passado no Runtime

```python
# Passar state na execução (sobrescreve o default)
agent.print_response(
    "What's in my session?",
    session_state={"shopping_list": ["Potatoes"]},
    stream=True,
)

# State é persistido e pode ser recuperado
print(f"Stored state: {agent.get_session_state()}")

# Próxima chamada com novo state sobrescreve
agent.print_response(
    "Check my state",
    session_state={"secret_number": 42},
    stream=True,
)
```

---

## Compartilhando State Entre Agentes

```python
from uuid import uuid4
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat

db = SqliteDb(db_file="tmp/shared.db")
session_id = str(uuid4())
user_id = "john_doe@example.com"

# Agente 1 - Amigável
agent_1 = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    instructions="You are really friendly and helpful.",
    db=db,
    add_history_to_context=True,
    enable_user_memories=True,
)

# Agente 2 - Técnico
agent_2 = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    instructions="You are technical and precise.",
    db=db,
    add_history_to_context=True,
    enable_user_memories=True,
)

# Ambos compartilham a mesma sessão
agent_1.print_response(
    "Hi! My name is John.",
    session_id=session_id,
    user_id=user_id,
)

# Agent 2 tem acesso ao histórico e memórias
agent_2.print_response(
    "What is my name?",
    session_id=session_id,
    user_id=user_id,
)
```

---

## State em Teams

```python
from agno.team import Team
from agno.db.postgres import PostgresDb
from agno.models.openai import OpenAIChat

db = PostgresDb(db_url="postgresql+psycopg://...")

team = Team(
    db=db,
    model=OpenAIChat(id="gpt-4o-mini"),
    members=[researcher, writer],
    instructions="User name is {user_name} and preferences: {preferences}",
)

# Criar sessão com state
team.print_response(
    "What is my name?",
    session_id="team_session_1",
    user_id="user_1",
    session_state={"user_name": "John", "preferences": {"style": "casual"}},
)

# Carregar state existente
team.print_response(
    "Remember my preferences?",
    session_id="team_session_1",
    user_id="user_1",
)
```

---

## Session IDs Automáticos

```python
# Se não fornecer session_id, o Agno gera um UUID automaticamente
agent = Agent(
    model=OpenAIChat(id="gpt-4o-mini"),
    db=db,
)

# Primeira execução - cria nova sessão
response = agent.run("Hello!")
print(f"Session ID: {response.session_id}")  # UUID gerado

# Para continuar a mesma sessão, use o mesmo session_id
agent.run("Continue our chat", session_id=response.session_id)
```

---

## Memória Persistente com Contexto Pequeno

### O Problema

Quando `NUM_HISTORY_RUNS` é baixo (ex: 3), o agente "esquece" informações das primeiras mensagens da conversa. Dados como nome do paciente, convênio e preferências se perdem após 3 turnos.

### A Solução: State + Injeção de Contexto

O template resolve isso com uma arquitetura de 3 camadas:

```
┌─────────────────────────────────────────────┐
│                INSTRUCTIONS                 │
│  (prompt base + contexto da sessão injetado)│
├─────────────────────────────────────────────┤
│             HISTORY (últimos N runs)        │
├─────────────────────────────────────────────┤
│              SESSION STATE (Redis)          │
│  • cliente: {nome, convenio, telefone, ...} │
│  • preferencias: {horario, dentista, ...}   │
│  • agendamentos: [...]                      │
└─────────────────────────────────────────────┘
```

**Como funciona:**

1. **Tools de estado** (`salvar_dados_cliente`, `salvar_preferencias`) gravam no `session_state`
2. O `session_state` é persistido no Redis entre runs
3. A cada novo run, `formatar_contexto_state()` gera um resumo textual do state
4. Esse resumo é **injetado nas instructions** do agente antes de criar a instância
5. O agente sempre "vê" os dados, mesmo que o histórico de mensagens já tenha rolado

### Tools de Memória

```python
from agno.tools import tool
from agno.run import RunContext

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
    """Salva dados cadastrais do cliente. Campos vazios não sobrescrevem."""
    state = run_context.session_state or {}
    if "cliente" not in state:
        state["cliente"] = {}
    if nome:
        state["cliente"]["nome"] = nome
    if convenio:
        state["cliente"]["convenio"] = convenio
    # ... outros campos
    run_context.session_state = state
    return "Dados salvos."

@tool
def salvar_preferencias(
    run_context: RunContext,
    chave: str,
    valor: str,
) -> str:
    """Salva preferência temporária (horário, dentista, alergias, etc.)."""
    state = run_context.session_state or {}
    if "preferencias" not in state:
        state["preferencias"] = {}
    state["preferencias"][chave] = {"valor": valor}
    run_context.session_state = state
    return f"Preferência salva: {chave} = {valor}"

@tool
def ver_contexto_sessao(run_context: RunContext) -> str:
    """Recupera todos os dados e preferências da sessão atual."""
    # Retorna resumo formatado do state
    ...
```

### Injeção de Contexto em main.py

```python
from app.tools import formatar_contexto_state

async def execute_agent(request, debug=False):
    instructions = await get_agent_instructions()
    session_state = await get_session_state(conversation_id)

    # Injeta state nas instructions para o agente não esquecer
    state_context = formatar_contexto_state(session_state)
    if state_context:
        instructions = instructions + state_context

    agent = create_agent(
        instructions=instructions,
        session_id=conversation_id,
        ...
    )
```

O `formatar_contexto_state()` gera algo como:

```
--- CONTEXTO DA SESSÃO (dados já coletados, NÃO pergunte novamente) ---
DADOS DO CLIENTE ATUAL: nome: João Pereira | convenio: OdontoPrev | telefone: (11) 98765-4321
PREFERÊNCIAS DO CLIENTE: horario_preferido: manhã | dentista_preferido: Dra. Maria
AGENDAMENTOS ATIVOS: CON-ABC123 - Limpeza em 2025-02-10 às 09:00 com Dra. Maria Silva
--- FIM DO CONTEXTO ---
```

### Instruções para o LLM

O prompt do agente DEVE incluir instruções de gestão de memória:

```
GESTÃO DE MEMÓRIA (CRÍTICO):
- SEMPRE use salvar_dados_cliente quando o paciente informar nome, telefone, e-mail, CPF ou convênio
- SEMPRE use salvar_preferencias quando o paciente mencionar horários preferidos, dentista preferido,
  alergias, medos ou qualquer observação relevante
- Use ver_contexto_sessao se precisar relembrar dados já coletados
- Se o CONTEXTO DA SESSÃO estiver presente nas instruções, use esses dados e NÃO pergunte novamente
- Ao agendar, use os dados do cliente já salvos no contexto da sessão
```

### Quando Usar Cada Tipo

| Tipo | Onde Armazenar | Duração | Exemplo |
|------|---------------|---------|---------|
| **Dados permanentes** | `session_state["cliente"]` via `salvar_dados_cliente` | Toda a sessão | Nome, CPF, convênio, telefone |
| **Preferências temporárias** | `session_state["preferencias"]` via `salvar_preferencias` | Toda a sessão | Horário preferido, dentista preferido, alergias |
| **Dados de operação** | `session_state["agendamentos"]` via tool específica | Toda a sessão | Consultas agendadas/canceladas |
| **Contexto conversacional** | History (automático) | Últimos N runs | O que foi dito recentemente |

### Configuração Recomendada

```bash
# Em .env
NUM_HISTORY_RUNS=3           # Contexto conversacional curto (economia de tokens)
ENABLE_USER_MEMORIES=true    # Agno salva memórias do usuário automaticamente
ENABLE_SESSION_SUMMARIES=true # Agno resume sessões anteriores
```

---

## Boas Práticas

| Prática | Descrição |
|---------|-----------|
| **Inicialize defaults** | Sempre defina `session_state` com valores padrão |
| **Use get()** | Acesse state com `.get()` para evitar KeyError |
| **Valide tipos** | O state pode ser modificado por tools, valide antes de usar |
| **Limpe dados sensíveis** | Não persista senhas ou tokens no state |
| **Use IDs consistentes** | Mantenha padrão para session_id e user_id |
| **Salve dados cedo** | Use `salvar_dados_cliente` assim que o paciente informar dados |
| **Instrua o LLM** | O prompt DEVE dizer ao agente para usar as tools de memória |
| **Injete contexto** | Use `formatar_contexto_state` para dados sobreviverem ao history rolloff |

---

## Referências

- [Agno State Management](https://docs.agno.com/basics/state/overview)
- [Agno Sessions](https://docs.agno.com/basics/sessions/session-management)
