# Input/Output (Schemas e Contrato AgentBench)

O sistema segue o contrato AgentBench com schemas Pydantic bem definidos para entrada e saida. Nao ha structured output do LLM -- o agente retorna texto livre via `AgentResponse.content`, que e encapsulado nos modelos de resposta.

---

## Conceitos

| Conceito | Descricao |
|----------|-----------|
| **RunRequest** | Schema de entrada com `list[InputItem]`, `conversation_id`, `model` |
| **RunResponse** | Resposta de producao com `FinalOutput` e `Metrics` |
| **RunDebugResponse** | Resposta de debug com trajetoria completa |
| **InputItem** | Item multimodal individual (texto, imagem, audio, etc.) |
| **FinalOutput** | Mensagem final do agente, estado da sessao e acoes executadas |
| **AgentResponse** | Resultado interno do agent loop (conteudo de texto, tokens, tools usadas) |

---

## Entrada: RunRequest

Definido em `app/models.py`. Enviado para os endpoints `/run` e `/run_debug`:

```python
from pydantic import BaseModel, Field
from typing import Literal

InputType = Literal['text', 'image', 'audio', 'document', 'video']

class InputItem(BaseModel):
    """Item de entrada multimodal."""
    type: InputType = Field(..., description='Tipo: text, image, audio, document, video')
    content: str = Field(..., description='Texto puro ou conteudo base64')
    filename: str | None = Field(None, description='Nome original do arquivo')
    mime_type: str | None = Field(None, description='Tipo MIME (ex: image/png)')

class RunRequest(BaseModel):
    """Requisicao para /run e /run_debug."""
    input: list[InputItem] = Field(..., min_length=1, max_length=20)
    conversation_id: str = Field(..., min_length=1)
    model: str | None = Field(None, description='Override opcional de modelo')
    received_at: float | None = Field(
        None, description='Timestamp Unix de quando a mensagem foi recebida pelo conector'
    )
```

### Exemplo de Request JSON

```json
{
  "input": [
    {"type": "text", "content": "Quais horarios disponiveis para amanha?"}
  ],
  "conversation_id": "conv-abc-123",
  "model": null
}
```

### Request Multimodal

```json
{
  "input": [
    {"type": "text", "content": "O que aparece nesta imagem?"},
    {
      "type": "image",
      "content": "iVBORw0KGgoAAAANSUh...",
      "mime_type": "image/png",
      "filename": "foto.png"
    }
  ],
  "conversation_id": "conv-abc-123"
}
```

### Limites

| Parametro | Limite |
|-----------|--------|
| `input` items | Minimo 1, maximo 20 |
| `conversation_id` | Minimo 1 caractere |
| `model` | Opcional -- usa `DEFAULT_MODEL` do `.env` se nao informado |

---

## Saida: RunResponse (Producao)

Retornado pelo endpoint `/run`. Definido em `app/models.py`:

```python
class ActionTaken(BaseModel):
    """Acao executada pelo agente."""
    tool: str
    success: bool
    error: str | None = None

class FinalOutput(BaseModel):
    """Saida final do agente."""
    message: str
    state: dict[str, Any] | None = None
    actions_taken: list[ActionTaken] | None = None

class Metrics(BaseModel):
    """Metricas de execucao."""
    latency_ms: float
    tokens_used: int | None = None
    cost_estimate: float | None = None

class RunResponse(BaseModel):
    """Resposta do endpoint /run."""
    conversation_id: str
    final_output: FinalOutput
    metrics: Metrics | None = None
```

### Exemplo de Response JSON

```json
{
  "conversation_id": "conv-abc-123",
  "final_output": {
    "message": "Temos horarios disponiveis amanha as 9h, 10h30 e 14h. Qual voce prefere?",
    "state": {
      "nome": "Maria Silva",
      "convenio": "OdontoPrev"
    },
    "actions_taken": [
      {"tool": "verificar_disponibilidade", "success": true, "error": null}
    ]
  },
  "metrics": {
    "latency_ms": 1234.56,
    "tokens_used": 850,
    "cost_estimate": null
  }
}
```

---

## Saida: RunDebugResponse (Debug)

Retornado pelo endpoint `/run_debug`. Inclui a trajetoria completa de execucao:

```python
class LLMCall(BaseModel):
    """Detalhes de uma chamada LLM."""
    model: str
    input_tokens: int
    output_tokens: int

class PromptDebug(BaseModel):
    """Informacoes de debug do prompt."""
    state_key: str | None = None
    state_value: str | None = None
    base_system_prompt: str | None = None
    final_system_prompt_used: str | None = None

class TrajectoryStage(BaseModel):
    """Estagio individual na trajetoria de execucao."""
    stage_id: str
    type: str = Field(..., description='agent, executor, router, memory, custom')
    sequence: int
    prompt_debug: PromptDebug | None = None
    llm_calls: list[LLMCall] | None = None
    output: dict[str, Any] | None = None
    errors: list[str] | None = None
    latency_ms: float

class DebugMetrics(BaseModel):
    """Metricas estendidas para modo debug."""
    total_latency_ms: float
    total_tokens: dict[str, int] | None = None
    llm_calls: int

class RunDebugResponse(BaseModel):
    """Resposta do endpoint /run_debug."""
    conversation_id: str
    final_output: FinalOutput
    trajectory: list[TrajectoryStage]
    metrics: DebugMetrics
```

### Exemplo de Response Debug JSON

```json
{
  "conversation_id": "conv-abc-123",
  "final_output": {
    "message": "Consulta agendada para amanha as 9h.",
    "state": {"nome": "Maria Silva"},
    "actions_taken": [
      {"tool": "verificar_disponibilidade", "success": true, "error": null},
      {"tool": "agendar_consulta", "success": true, "error": null}
    ]
  },
  "trajectory": [
    {
      "stage_id": "main",
      "type": "agent",
      "sequence": 1,
      "prompt_debug": {
        "final_system_prompt_used": "Voce e um assistente..."
      },
      "llm_calls": [
        {
          "model": "claude-sonnet-4-20250514",
          "input_tokens": 1200,
          "output_tokens": 350
        }
      ],
      "latency_ms": 2345.67
    }
  ],
  "metrics": {
    "total_latency_ms": 2345.67,
    "total_tokens": {"input": 1200, "output": 350},
    "llm_calls": 1
  }
}
```

---

## AgentResponse (Interno)

O resultado interno do agent loop (`app/agent_loop.py`) e um dataclass, nao um schema de API:

```python
@dataclass
class AgentResponse:
    """Resultado do agent loop."""
    content: str                              # Texto final do agente
    messages: list[dict[str, Any]]            # Historico completo de mensagens
    input_tokens: int = 0                     # Total de tokens de entrada
    output_tokens: int = 0                    # Total de tokens de saida
    tools_used: list[str] = field(default_factory=list)  # Nomes das tools chamadas
    session_state: dict[str, Any] = field(default_factory=dict)  # Estado atualizado
```

O `AgentResponse.content` e uma string de texto livre -- o agente nao retorna JSON estruturado. O texto e encapsulado em `FinalOutput.message` na resposta da API.

---

## Fluxo Completo: Request ate Response

```
POST /run (RunRequest)
    |
    v
parse_multimodal_input(request.input)   --> (text_message, images)
    |
    v
get_session_state(conversation_id)       --> session_state (Redis)
get_agent_instructions()                 --> template do prompt
get_memory_context(conversation_id)      --> fatos consolidados
    |
    v
compile_prompt(template, session_context)
build_system_messages(instructions, text, images, history)
    |
    v
run_agent_loop(messages, tools, run_context, model)
    |   |
    |   +-- litellm.acompletion() --> tool_calls?
    |   |   +-- Sim --> ToolRegistry.execute() --> repete
    |   |   +-- Nao --> AgentResponse(content=..., tokens=..., tools_used=...)
    |   |
    |   +-- RetryAgentRun --> feedback como tool result, continua
    |   +-- StopAgentRun  --> para imediatamente
    |
    v
extract_response_text(response)          --> string da mensagem
extract_actions_from_response(response)  --> list[ActionTaken]
    |
    v
RunResponse(
    conversation_id=...,
    final_output=FinalOutput(message=..., state=..., actions_taken=...),
    metrics=Metrics(latency_ms=..., tokens_used=...)
)
```

---

## Endpoint /metadata

O endpoint `/metadata` declara as capacidades do modulo, incluindo tipos de entrada suportados:

```json
{
  "module_id": "meu-agente",
  "version": "1.0.0",
  "capabilities": {
    "supports_multi_stage": false,
    "supports_dynamic_system_prompt": true,
    "supports_cross_model": true,
    "supports_jailbreak_tests": true
  },
  "input_types": {
    "supported_types": ["text", "image", "audio"],
    "allowed_formats": {
      "image": ["jpeg", "jpg", "png", "webp"],
      "audio": ["mp3", "wav", "ogg"]
    }
  },
  "tools_exposed": [
    {"name": "listar_servicos", "description": "..."},
    {"name": "verificar_disponibilidade", "description": "..."}
  ]
}
```

---

## Tratamento de Erros

Quando ocorre um erro na execucao do agente, a resposta ainda segue o schema padrao:

### /run com erro

```json
{
  "conversation_id": "conv-abc-123",
  "final_output": {
    "message": "An error occurred while processing your request.",
    "state": null,
    "actions_taken": null
  },
  "metrics": {
    "latency_ms": 150.0,
    "tokens_used": null,
    "cost_estimate": null
  }
}
```

### /run_debug com erro

```json
{
  "conversation_id": "conv-abc-123",
  "final_output": {
    "message": "An error occurred: Connection timeout",
    "state": null,
    "actions_taken": null
  },
  "trajectory": [
    {
      "stage_id": "error",
      "type": "agent",
      "sequence": 1,
      "prompt_debug": {"final_system_prompt_used": "Error occurred"},
      "llm_calls": [],
      "latency_ms": 150.0,
      "errors": ["Connection timeout"]
    }
  ],
  "metrics": {
    "total_latency_ms": 150.0,
    "total_tokens": {"input": 0, "output": 0},
    "llm_calls": 0
  }
}
```

---

## Validacao Customizada

Como os schemas usam Pydantic v2, voce pode adicionar validadores customizados:

```python
from pydantic import BaseModel, Field, field_validator

class InputItem(BaseModel):
    type: InputType
    content: str
    filename: str | None = None
    mime_type: str | None = None

    @field_validator('content')
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Conteudo nao pode ser vazio')
        return v

    @field_validator('mime_type')
    @classmethod
    def validate_mime(cls, v: str | None) -> str | None:
        if v and '/' not in v:
            raise ValueError('MIME type invalido')
        return v
```

---

## Boas Praticas

| Pratica | Descricao |
|---------|-----------|
| **Sempre envie conversation_id** | Necessario para historico, estado e memoria |
| **Use Field()** | Adicione descriptions nos campos para documentacao automatica |
| **Valide no schema** | Use min_length, max_length, ge, le no Pydantic |
| **Trate erros no response** | Verifique se `actions_taken` contem erros |
| **Use /run_debug** | Para investigar problemas, use o endpoint debug com trajetoria |
| **Nao espere JSON estruturado** | O agente retorna texto livre; use tools para acoes estruturadas |

---

## Referencias

- [Pydantic v2 Documentation](https://docs.pydantic.dev/)
- [FastAPI Request/Response](https://fastapi.tiangolo.com/tutorial/response-model/)
- [LiteLLM Completion](https://docs.litellm.ai/docs/completion/input)
