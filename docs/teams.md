# Multi-Agent Teams

Teams permitem coordenar multiplos agentes especializados para resolver tarefas complexas. Um agente "lider" roteia sub-tarefas para agentes membros, cada um com suas proprias instrucoes e ferramentas.

---

## Abordagem

Multi-agent e implementado chamando `run_agent_loop()` multiplas vezes com diferentes configuracoes, tools e instrucoes, usando um padrao de roteamento.

---

## Como Implementar

### 1. Padrao Router: Agente Roteador

O agente principal decide qual "membro" (configuracao) deve processar a tarefa:

```python
# app/teams.py

from app.agent import build_system_messages, get_litellm_model
from app.agent_loop import AgentResponse, run_agent_loop
from app.runtime import RunContext, ToolRegistry, tool


# Definir configuracoes dos agentes membros
AGENT_CONFIGS = {
    "pesquisador": {
        "instructions": "Voce e um pesquisador. Busque informacoes e forneca resumos factuais.",
        "tools": ["buscar_web", "buscar_documentos"],
    },
    "redator": {
        "instructions": "Voce e um redator. Escreva conteudo claro e engajante.",
        "tools": ["formatar_texto"],
    },
    "analista": {
        "instructions": "Voce e um analista de dados. Analise dados e forneca insights.",
        "tools": ["calcular", "gerar_grafico"],
    },
}


async def executar_membro(
    membro: str,
    tarefa: str,
    run_context: RunContext,
    model: str,
) -> AgentResponse:
    """Executa um agente membro especifico."""
    config = AGENT_CONFIGS[membro]

    # Montar registry com tools do membro
    registry = ToolRegistry()
    # ... registrar tools especificas do membro

    messages = build_system_messages(
        instructions=config["instructions"],
        text_message=tarefa,
    )

    return await run_agent_loop(
        messages=messages,
        tools=registry,
        run_context=run_context,
        model=model,
    )
```

### 2. Roteamento via Tool

O agente principal usa uma tool para delegar tarefas:

```python
# app/tools/delegar.py

from app.runtime import tool, RunContext


@tool
def delegar_tarefa(run_context: RunContext, membro: str, tarefa: str) -> str:
    """Delega uma tarefa para um agente membro especializado.

    Args:
        membro: Nome do membro (pesquisador, redator, analista).
        tarefa: Descricao da tarefa a ser delegada.
    """
    # Nota: como tools sao sincronas, armazene a delegacao
    # no session_state para processamento posterior
    if "delegacoes" not in run_context.session_state:
        run_context.session_state["delegacoes"] = []

    run_context.session_state["delegacoes"].append({
        "membro": membro,
        "tarefa": tarefa,
    })

    return f"Tarefa delegada para {membro}: {tarefa}"
```

### 3. Orquestracao Sequencial (Coordinate)

O lider coordena os membros e sintetiza os resultados:

```python
# app/teams.py

async def coordenar_time(
    tarefa: str,
    membros: list[str],
    run_context: RunContext,
    model: str,
) -> str:
    """Coordena multiplos agentes em sequencia."""
    resultados = {}

    for membro in membros:
        response = await executar_membro(
            membro=membro,
            tarefa=tarefa,
            run_context=run_context,
            model=model,
        )
        resultados[membro] = response.content

    # Agente sintetizador combina os resultados
    sintese_prompt = "Combine os seguintes resultados:\n"
    for membro, resultado in resultados.items():
        sintese_prompt += f"\n## {membro}\n{resultado}\n"

    messages = build_system_messages(
        instructions="Sintetize os resultados dos membros do time em uma resposta coesa.",
        text_message=sintese_prompt,
    )

    final = await run_agent_loop(
        messages=messages,
        tools=ToolRegistry(),  # Sem tools, apenas sintese
        run_context=run_context,
        model=model,
    )

    return final.content
```

### 4. Roteamento Direto (Route)

O roteador analisa a tarefa e delega ao membro mais adequado:

```python
# app/teams.py

async def rotear_tarefa(
    tarefa: str,
    run_context: RunContext,
    model: str,
) -> AgentResponse:
    """Roteia a tarefa para o membro mais adequado."""
    # Primeiro, o roteador decide qual membro usar
    router_instructions = (
        "Analise a tarefa e responda APENAS com o nome do membro "
        "mais adequado: pesquisador, redator, ou analista."
    )
    messages = build_system_messages(
        instructions=router_instructions,
        text_message=tarefa,
    )

    router_response = await run_agent_loop(
        messages=messages,
        tools=ToolRegistry(),
        run_context=run_context,
        model=model,
    )

    membro = router_response.content.strip().lower()

    # Depois, executa o membro escolhido
    return await executar_membro(
        membro=membro,
        tarefa=tarefa,
        run_context=run_context,
        model=model,
    )
```

---

## Resumo

| Modo | Descricao |
|------|-----------|
| Definicao de membros | Dicionario `AGENT_CONFIGS` + chamadas multiplas a `run_agent_loop()` |
| Coordenacao | `coordenar_time()` -- executa membros e sintetiza |
| Roteamento | `rotear_tarefa()` -- roteador escolhe membro |
| Colaboracao | Executar todos os membros em paralelo com `asyncio.gather()` |
| Hooks globais | Hooks globais no `ToolRegistry` compartilhado |
