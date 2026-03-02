# Streaming e Eventos

Streaming permite enviar respostas parciais ao cliente conforme o agente as gera, em vez de esperar a resposta completa.

---

## Abordagem

O template atual usa `litellm.acompletion()` que retorna a resposta completa de uma vez. Streaming pode ser implementado usando o suporte nativo do LiteLLM.

---

## Como Implementar Streaming

### 1. Streaming Basico com LiteLLM

O LiteLLM suporta streaming via parametro `stream=True`:

```python
import litellm


async def stream_response(model: str, messages: list[dict]):
    """Stream de resposta do LLM."""
    response = await litellm.acompletion(
        model=model,
        messages=messages,
        stream=True,
    )

    async for chunk in response:
        content = chunk.choices[0].delta.content
        if content:
            yield content
```

### 2. Endpoint SSE (Server-Sent Events)

Para expor streaming via API, use `StreamingResponse` do FastAPI:

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.agent import build_system_messages, get_litellm_model


@app.post("/chat/stream")
async def chat_stream(message: str, model: str = None):
    """Endpoint de streaming via SSE."""
    litellm_model = get_litellm_model(model)
    messages = build_system_messages(
        instructions="Voce e um assistente util.",
        text_message=message,
    )

    async def generate():
        response = await litellm.acompletion(
            model=litellm_model,
            messages=messages,
            stream=True,
        )
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield f"data: {content}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )
```

### 3. Streaming com Tool Calling

Streaming com tool calling requer tratamento especial — tool calls chegam em chunks parciais:

```python
import json
import litellm


async def stream_with_tools(
    model: str,
    messages: list[dict],
    tools: list[dict],
):
    """Stream com suporte a tool calling."""
    response = await litellm.acompletion(
        model=model,
        messages=messages,
        tools=tools,
        stream=True,
    )

    tool_calls_buffer = {}
    async for chunk in response:
        delta = chunk.choices[0].delta

        # Conteudo de texto
        if delta.content:
            yield {"type": "content", "data": delta.content}

        # Tool calls (chegam em chunks parciais)
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_buffer:
                    tool_calls_buffer[idx] = {
                        "id": tc.id or "",
                        "name": tc.function.name or "",
                        "arguments": "",
                    }
                if tc.id:
                    tool_calls_buffer[idx]["id"] = tc.id
                if tc.function.name:
                    tool_calls_buffer[idx]["name"] = tc.function.name
                if tc.function.arguments:
                    tool_calls_buffer[idx]["arguments"] += tc.function.arguments

        # Fim do stream
        if chunk.choices[0].finish_reason == "tool_calls":
            for tc_data in tool_calls_buffer.values():
                yield {"type": "tool_call", "data": tc_data}
```

### 4. Agent Loop com Streaming

Para implementar streaming completo no agent loop, seria necessario modificar `run_agent_loop()` em `app/agent_loop.py`:

```python
# app/agent_loop.py (versao streaming)

async def run_agent_loop_streaming(
    messages: list[dict],
    tools,
    run_context,
    model: str,
    max_iterations: int = 10,
):
    """Agent loop com streaming de respostas parciais."""
    for iteration in range(max_iterations):
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            tools=tools.get_definitions() if tools else None,
            stream=True,
        )

        content_parts = []
        tool_calls = []

        async for chunk in response:
            delta = chunk.choices[0].delta

            if delta.content:
                content_parts.append(delta.content)
                yield {"type": "content", "data": delta.content}

            # Acumular tool calls...
            # (mesmo padrao do exemplo anterior)

        # Se houve tool calls, executar e continuar loop
        if tool_calls:
            for tc in tool_calls:
                result = await tools.execute(
                    tc["name"],
                    json.loads(tc["arguments"]),
                    run_context,
                )
                yield {"type": "tool_result", "data": {
                    "tool": tc["name"],
                    "result": result[:500],
                }}
                messages.append(...)  # tool result
            continue

        # Sem tool calls = resposta final
        break
```

---

## Limitacoes Atuais

O template nao implementa streaming nativamente nos endpoints `/run` e `/run_debug`. Esses endpoints retornam a resposta completa como JSON.

Para adicionar streaming:

1. Criar novo endpoint `/run/stream` com `StreamingResponse`
2. Implementar `run_agent_loop_streaming()` no `agent_loop.py`
3. Tratar tool calls parciais no stream
4. Manter endpoints existentes para compatibilidade

---

## Resumo

| Funcionalidade | Como Implementar |
|----------------|------------------|
| Streaming basico | `litellm.acompletion(..., stream=True)` |
| Conteudo parcial | `chunk.choices[0].delta.content` |
| Tool calls em stream | `chunk.choices[0].delta.tool_calls` |
| Streaming async | `await litellm.acompletion(..., stream=True)` |
| Eventos separados | Tratar `delta.content` e `delta.tool_calls` separadamente |
| Streaming em FastAPI | `StreamingResponse` com `text/event-stream` |

---

## Referencias

- [LiteLLM Streaming](https://docs.litellm.ai/docs/completion/stream)
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
