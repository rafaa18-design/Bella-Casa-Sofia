# Workflows

Workflows permitem orquestrar multiplos passos em pipelines complexos, onde a saida de um passo alimenta o proximo. Sao uteis para processos que envolvem pesquisa, analise, revisao e publicacao em sequencia.

---

## Abordagem

Workflows sequenciais sao implementados como funcoes async Python que chamam `run_agent_loop()` em sequencia com diferentes instrucoes e tools.

---

## Como Implementar

### 1. Workflow como Funcao Async

Um workflow e simplesmente uma funcao que encadeia chamadas:

```python
# app/workflows.py

import logging
from dataclasses import dataclass, field
from typing import Any

from app.agent import build_system_messages, get_litellm_model
from app.agent_loop import run_agent_loop
from app.runtime import RunContext, ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Resultado de um workflow."""
    content: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0


async def pipeline_conteudo(
    topico: str,
    run_context: RunContext,
    model: str | None = None,
) -> WorkflowResult:
    """Workflow: Pesquisa -> Redacao -> Revisao."""
    model = model or get_litellm_model()
    result = WorkflowResult(content="")

    # === PASSO 1: Pesquisa ===
    messages = build_system_messages(
        instructions="Voce e um pesquisador. Busque informacoes detalhadas sobre o topico.",
        text_message=f"Pesquise sobre: {topico}",
    )
    pesquisa = await run_agent_loop(
        messages=messages,
        tools=ToolRegistry(),  # Adicionar tools de busca se necessario
        run_context=run_context,
        model=model,
    )
    result.steps.append({"name": "Pesquisa", "output": pesquisa.content})
    result.total_tokens += pesquisa.input_tokens + pesquisa.output_tokens

    # === PASSO 2: Redacao ===
    messages = build_system_messages(
        instructions="Voce e um redator. Escreva um artigo claro e engajante baseado na pesquisa.",
        text_message=f"Baseado nesta pesquisa, escreva um artigo:\n\n{pesquisa.content}",
    )
    redacao = await run_agent_loop(
        messages=messages,
        tools=ToolRegistry(),
        run_context=run_context,
        model=model,
    )
    result.steps.append({"name": "Redacao", "output": redacao.content})
    result.total_tokens += redacao.input_tokens + redacao.output_tokens

    # === PASSO 3: Revisao ===
    messages = build_system_messages(
        instructions="Voce e um revisor. Revise o texto para clareza, gramatica e tom.",
        text_message=f"Revise este artigo:\n\n{redacao.content}",
    )
    revisao = await run_agent_loop(
        messages=messages,
        tools=ToolRegistry(),
        run_context=run_context,
        model=model,
    )
    result.steps.append({"name": "Revisao", "output": revisao.content})
    result.total_tokens += revisao.input_tokens + revisao.output_tokens

    result.content = revisao.content
    return result
```

### 2. Workflow com Condicoes

Adicione logica condicional entre os passos:

```python
# app/workflows.py

async def workflow_condicional(
    mensagem: str,
    run_context: RunContext,
    model: str | None = None,
) -> WorkflowResult:
    """Workflow com passos condicionais."""
    model = model or get_litellm_model()
    result = WorkflowResult(content="")

    # Verificar condicao: usuario ja foi saudado?
    if not run_context.session_state.get("has_been_greeted"):
        messages = build_system_messages(
            instructions="Saude o usuario de forma calorosa e profissional.",
            text_message=mensagem,
        )
        saudacao = await run_agent_loop(
            messages=messages,
            tools=ToolRegistry(),
            run_context=run_context,
            model=model,
        )
        run_context.session_state["has_been_greeted"] = True
        result.steps.append({"name": "Saudacao", "output": saudacao.content})

    # Passo principal (sempre executa)
    messages = build_system_messages(
        instructions="Voce e um assistente. Responda a pergunta do usuario.",
        text_message=mensagem,
    )
    resposta = await run_agent_loop(
        messages=messages,
        tools=ToolRegistry(),
        run_context=run_context,
        model=model,
    )
    result.steps.append({"name": "Resposta", "output": resposta.content})
    result.content = resposta.content

    return result
```

### 3. Workflow com Passos Paralelos

Use `asyncio.gather()` para executar passos independentes em paralelo:

```python
# app/workflows.py

import asyncio


async def workflow_paralelo(
    topico: str,
    run_context: RunContext,
    model: str | None = None,
) -> WorkflowResult:
    """Workflow com passos paralelos."""
    model = model or get_litellm_model()

    # Executar pesquisas em paralelo
    async def pesquisar(subtopico: str):
        messages = build_system_messages(
            instructions="Pesquise informacoes sobre o subtopico.",
            text_message=subtopico,
        )
        return await run_agent_loop(
            messages=messages,
            tools=ToolRegistry(),
            run_context=run_context,
            model=model,
        )

    resultados = await asyncio.gather(
        pesquisar(f"{topico} - aspectos tecnicos"),
        pesquisar(f"{topico} - impacto no mercado"),
        pesquisar(f"{topico} - tendencias futuras"),
    )

    # Combinar resultados em passo final
    combinado = "\n\n".join(r.content for r in resultados)

    messages = build_system_messages(
        instructions="Sintetize as pesquisas em um relatorio unico e coeso.",
        text_message=combinado,
    )
    final = await run_agent_loop(
        messages=messages,
        tools=ToolRegistry(),
        run_context=run_context,
        model=model,
    )

    return WorkflowResult(content=final.content)
```

---

## Resumo

| Componente | Descricao |
|------------|-----------|
| Workflow sequencial | Funcao async que chama `run_agent_loop()` em sequencia |
| Passo com agente | Chamada a `run_agent_loop()` com instrucoes especificas |
| Passo com logica | Funcao Python normal entre chamadas de `run_agent_loop()` |
| Condicoes | `if/else` em Python antes de um passo |
| Resultado de passo | `AgentResponse` de `app/agent_loop` |
| Passos paralelos | `asyncio.gather()` com multiplas chamadas |
