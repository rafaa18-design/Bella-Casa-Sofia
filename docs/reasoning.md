# Reasoning (Raciocinio)

Reasoning (raciocinio estruturado) permite que o agente "pense passo a passo" antes de responder, melhorando a qualidade das respostas em tarefas complexas como analise logica, matematica, tomada de decisao e resolucao de problemas.

---

## Abordagens Disponiveis

Raciocinio estruturado pode ser alcancado de duas formas:
1. **Prompt engineering**: Instrucoes de chain-of-thought no system prompt
2. **Extended thinking nativo**: Parametro `thinking` do Claude via LiteLLM

---

## Como Implementar

### 1. Chain-of-Thought via Prompt Engineering

A forma mais simples -- adicione instrucoes de raciocinio ao system prompt:

```python
# app/agent.py ou no template Langfuse

REASONING_INSTRUCTIONS = """
Antes de responder, siga este processo de raciocinio:

1. **Entender**: Reformule o problema nas suas proprias palavras.
2. **Analisar**: Identifique os fatores e restricoes relevantes.
3. **Avaliar**: Considere diferentes abordagens ou perspectivas.
4. **Concluir**: Chegue a uma conclusao fundamentada.
5. **Responder**: Forneca a resposta final de forma clara.

Mostre seu raciocinio antes da resposta final.
"""
```

Injetar no `build_system_messages()`:

```python
# app/agent.py

def build_system_messages(
    instructions: str,
    text_message: str,
    enable_reasoning: bool = False,
    **kwargs,
) -> list[dict]:
    if enable_reasoning:
        instructions = f"{instructions}\n\n{REASONING_INSTRUCTIONS}"

    messages = [{"role": "system", "content": instructions}]
    # ... resto da construcao
    return messages
```

### 2. Extended Thinking do Claude (via LiteLLM)

Claude suporta "extended thinking" nativo -- o modelo raciocina internamente antes de responder. Isso e passado via parametro `thinking` na chamada do LiteLLM:

```python
# app/agent_loop.py (modificar run_agent_loop)

import litellm


async def run_agent_loop(
    messages: list[dict],
    tools,
    run_context,
    model: str,
    enable_thinking: bool = False,
    thinking_budget: int = 10000,
    **kwargs,
):
    # Parametros extras para extended thinking
    extra_params = {}
    if enable_thinking and "claude" in model.lower():
        extra_params["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        tools=tools.to_openai_format() if tools else None,
        **extra_params,
    )
    # O conteudo de "thinking" vem em response.choices[0].message.thinking
    # O conteudo final vem em response.choices[0].message.content
```

### 3. Habilitar no execute_agent

```python
# app/main.py (dentro de execute_agent)

response = await run_agent_loop(
    messages=messages,
    tools=tools,
    run_context=run_context,
    model=model,
    enable_thinking=request.extra_params.get("enable_thinking", False),
    thinking_budget=request.extra_params.get("thinking_budget", 10000),
)
```

### 4. Tool de Raciocinio Explicito

Crie uma tool que forca o agente a pensar antes de agir:

```python
# app/tools/raciocinar.py

from app.runtime import tool


@tool
def pensar(raciocinio: str) -> str:
    """Use esta ferramenta para organizar seu pensamento antes de responder.

    Sempre use esta ferramenta para tarefas complexas que exigem
    analise cuidadosa. Escreva seu raciocinio passo a passo.

    Args:
        raciocinio: Seu processo de raciocinio detalhado.
    """
    # A tool apenas retorna o raciocinio -- o importante e que o modelo
    # e forcado a articular seu pensamento como chamada de tool
    return f"Raciocinio registrado. Continue com base nesta analise."
```

Registre em `get_tools_registry()`:

```python
# app/agent.py

from app.tools.raciocinar import pensar


def get_tools_registry() -> ToolRegistry:
    registry = ToolRegistry()
    all_tools = [
        pensar,  # Tool de raciocinio
        # ... outras tools
    ]
    for t in all_tools:
        registry.register(t)
    return registry
```

---

## Comparacao de Abordagens

| Abordagem | Vantagem | Desvantagem |
|-----------|----------|-------------|
| **Prompt engineering** | Simples, funciona com qualquer modelo | Raciocinio visivel no output |
| **Extended thinking (Claude)** | Raciocinio interno profundo, nao polui output | Apenas Claude, consome mais tokens |
| **Tool de raciocinio** | Raciocinio visivel nos logs de tools | Consome uma chamada de tool |

---

## Resumo

| Funcionalidade | Como Implementar |
|----------------|------------------|
| Chain-of-thought | Instrucoes chain-of-thought no system prompt |
| Tool de raciocinio | Tool `pensar()` com `@tool` decorator |
| Extended thinking (Claude) | Parametro `thinking.budget_tokens` via LiteLLM |
| Raciocinio separado | Chamada separada a `run_agent_loop()` com instrucoes de raciocinio |
| Visualizar raciocinio | Acessar `response.choices[0].message.thinking` do LiteLLM |
