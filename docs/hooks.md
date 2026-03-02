# Hooks (Pre/Post Processamento)

Hooks permitem interceptar e modificar o comportamento do agente em diferentes pontos da execucao -- antes de processar o input, apos obter a resposta, ou envolvendo chamadas de tools.

---

## Implementacao

O sistema utiliza LiteLLM + agent loop proprio, onde hooks sao implementados diretamente no pipeline de execucao do agente.

---

## Como Implementar

### 1. Pre/Post Hook no Pipeline do Agente

A funcao `execute_agent()` em `app/main.py` e o ponto central de execucao. Adicione logica antes e depois de `run_agent_loop()`:

```python
# app/main.py (dentro de execute_agent)

from app.agent_loop import run_agent_loop

async def execute_agent(request, debug=False):
    text_message, images = parse_multimodal_input(request.input)

    # === PRE-HOOK: antes do agente processar ===
    text_message = await pre_process_input(text_message)

    # Execucao normal do agente
    response = await run_agent_loop(
        messages=messages,
        tools=tools,
        run_context=run_context,
        model=model,
    )

    # === POST-HOOK: apos o agente responder ===
    response = await post_process_output(response)

    return response
```

### 2. Pre-Hook: Transformacao de Input

```python
# app/hooks.py

import re
import logging

logger = logging.getLogger(__name__)


async def pre_process_input(text: str) -> str:
    """Pre-hook: transforma o input antes do agente processar."""
    logger.info(f"[PRE-HOOK] Input original: {text[:100]}")

    # Exemplo: normalizar texto
    text = text.strip()

    # Exemplo: remover URLs
    text = re.sub(r'https?://\S+', '[URL removida]', text)

    return text
```

### 3. Post-Hook: Transformacao de Output

```python
# app/hooks.py

from app.agent_loop import AgentResponse


async def post_process_output(response: AgentResponse) -> AgentResponse:
    """Post-hook: transforma a resposta apos o agente processar."""
    logger.info(f"[POST-HOOK] Tokens usados: {response.input_tokens + response.output_tokens}")

    # Exemplo: adicionar disclaimer
    if "investimento" in response.content.lower():
        response.content += "\n\n_Nota: isto nao constitui aconselhamento financeiro._"

    return response
```

### 4. Tool Hooks (Wrappers ao Redor de Tools)

Para interceptar execucoes de tools individuais, crie um wrapper no registro de tools:

```python
# app/tools/minha_tool.py

import time
import logging
from app.runtime import tool

logger = logging.getLogger(__name__)


def com_logging(func):
    """Decorator que adiciona pre/post hooks a uma tool."""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Pre-hook
        logger.info(f"[TOOL-PRE] Chamando: {func.__name__} args={kwargs}")
        start = time.time()

        result = func(*args, **kwargs)

        # Post-hook
        duration = time.time() - start
        logger.info(f"[TOOL-POST] {func.__name__} completou em {duration:.2f}s")
        return result

    # Preservar metadados para o @tool decorator
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


@tool
@com_logging
def buscar_dados(query: str) -> str:
    """Busca dados no sistema."""
    return f"Resultados para: {query}"
```

### 5. Hook Global no Agent Loop

Para interceptar **todas** as chamadas de tools, modifique o `ToolRegistry.execute()` em `app/runtime.py`:

```python
# Em app/runtime.py, dentro de ToolRegistry

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDef] = {}
        self._hooks: list[Callable] = []  # Lista de hooks globais

    def add_hook(self, hook: Callable):
        """Adiciona um hook global executado em cada chamada de tool."""
        self._hooks.append(hook)

    async def execute(self, name, arguments, run_context):
        # Executar pre-hooks
        for hook in self._hooks:
            hook(name, arguments, "pre")

        result = ...  # execucao normal

        # Executar post-hooks
        for hook in self._hooks:
            hook(name, arguments, "post", result)

        return result
```

---

## Resumo

| Tipo de Hook | Onde Implementar |
|-------------|-----------------|
| **Pre-processamento de input** | `execute_agent()` em `app/main.py`, antes de `run_agent_loop()` |
| **Pos-processamento de output** | `execute_agent()` em `app/main.py`, apos `run_agent_loop()` |
| **Hook por tool individual** | Decorator wrapper na propria tool |
| **Hook global em todas as tools** | `ToolRegistry` em `app/runtime.py` |
