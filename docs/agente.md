# Configuracao do Agente

Este documento cobre a configuracao do agente baseado em **LiteLLM + agent loop proprio**, incluindo modelos, ferramentas, memoria e personalizacao de comportamento.

---

## Visao Geral da Arquitetura

O agente utiliza uma arquitetura sem framework externo, composta por:

| Modulo | Arquivo | Responsabilidade |
|--------|---------|-----------------|
| **Runtime** | `app/runtime.py` | `RunContext`, `@tool`, `ToolRegistry`, excecoes |
| **Agent** | `app/agent.py` | Funcoes utilitarias: modelo, registro de tools, messages |
| **Agent Loop** | `app/agent_loop.py` | Loop iterativo de tool-calling com `litellm.acompletion()` |
| **Config** | `app/config.py` | Todas as configuracoes via `pydantic-settings` |
| **Memoria** | `app/memory.py` | Consolidacao LLM-driven de memoria de longo prazo |

### Fluxo de Execucao

```
Request
  -> build_system_messages(instructions, text, images, history)
  -> run_agent_loop(messages, tools, run_context, model)
       |
       +-> litellm.acompletion() -> tem tool_calls?
       |     Sim -> ToolRegistry.execute() -> adiciona resultado -> repete
       |     Nao -> retorna AgentResponse(content, tokens, tools_used)
       |
       +-> RetryAgentRun  -> feedback como tool result, continua loop
       +-> StopAgentRun   -> para loop imediatamente
  -> Consolidacao de memoria (background, se MEMORY_WINDOW atingido)
  -> Retorna resposta
```

---

## Configuracao de Modelo

### Como o modelo e resolvido

A funcao `get_litellm_model()` em `app/agent.py` converte o ID do modelo para o formato LiteLLM, que usa o padrao `provider/modelo`:

```python
# app/agent.py

def get_litellm_model(model_id: str | None = None) -> str:
    """Retorna string litellm para o modelo."""
    model_id = model_id or settings.DEFAULT_MODEL

    # Vertex AI (IDs contem @)
    if '@' in model_id or settings.MODEL_PROVIDER == 'vertexai':
        return f'vertex_ai/{model_id}'

    # Anthropic Claude
    if 'claude' in model_id.lower():
        return f'anthropic/{model_id}'

    # OpenAI
    if 'gpt' in model_id.lower() or 'o1' in model_id.lower():
        return f'openai/{model_id}'

    # Default: passa direto (litellm suporta diversos providers)
    return model_id
```

### Modelos por Provider

Todos os modelos sao strings LiteLLM no formato `provider/modelo`.

#### Anthropic (API direta)

```python
# .env
MODEL_PROVIDER=anthropic
DEFAULT_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-ant-...

# Resultado de get_litellm_model():
# "anthropic/claude-sonnet-4-20250514"
```

#### OpenAI

```python
# .env
MODEL_PROVIDER=openai
DEFAULT_MODEL=gpt-5-mini
OPENAI_API_KEY=sk-...

# Resultado de get_litellm_model():
# "openai/gpt-5-mini"
```

#### Vertex AI (Google Cloud)

```python
# .env
MODEL_PROVIDER=vertexai
DEFAULT_MODEL=claude-sonnet-4@20250514
GOOGLE_CLOUD_PROJECT=meu-projeto
GOOGLE_CLOUD_REGION=us-east5
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Resultado de get_litellm_model():
# "vertex_ai/claude-sonnet-4@20250514"
```

#### Outros providers suportados pelo LiteLLM

O LiteLLM suporta dezenas de providers. Se o ID do modelo nao for reconhecido pela factory, ele e passado diretamente ao LiteLLM. Exemplos:

```bash
# AWS Bedrock
DEFAULT_MODEL=bedrock/anthropic.claude-3-sonnet-20240229-v1:0

# Ollama (local)
DEFAULT_MODEL=ollama/llama3.2

# Azure OpenAI
DEFAULT_MODEL=azure/meu-deploy-gpt4
```

Consulte a [documentacao do LiteLLM](https://docs.litellm.ai/docs/providers) para a lista completa de providers e formatos.

### Parametros de Geracao

Os parametros de geracao (temperatura, max tokens) sao configurados via variaveis de ambiente e passados diretamente ao `litellm.acompletion()`:

```python
# .env
MAX_OUTPUT_TOKENS=2048

# Em app/agent_loop.py, os parametros sao passados ao litellm:
response = await litellm.acompletion(
    model=model,              # ex: "anthropic/claude-sonnet-4-20250514"
    messages=messages,
    tools=tool_definitions,
    tool_choice='auto',
    temperature=0.1,          # Configuravel no run_agent_loop()
    max_tokens=max_tokens,    # Vem de settings.MAX_OUTPUT_TOKENS
)
```

### Trocar de Modelo

Para trocar o modelo do agente, basta alterar as variaveis de ambiente:

```bash
# De OpenAI para Anthropic
DEFAULT_MODEL=claude-sonnet-4-20250514
MODEL_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# De Anthropic para Vertex AI
DEFAULT_MODEL=claude-sonnet-4@20250514
MODEL_PROVIDER=vertexai
GOOGLE_CLOUD_PROJECT=meu-projeto
GOOGLE_CLOUD_REGION=us-east5
```

Nao e necessario alterar nenhum codigo. A funcao `get_litellm_model()` detecta o provider automaticamente.

---

## Configuracao de Ferramentas (Tools)

### O decorator `@tool`

O decorator `@tool` de `app/runtime.py` converte uma funcao Python em um `ToolDefinition` com schema JSON compativel com a OpenAI Tool Calling API:

```python
from app.runtime import tool

@tool
def minha_ferramenta(parametro: str) -> str:
    """Descricao da ferramenta para o LLM.

    O LLM usa esta descricao para decidir quando chamar a ferramenta.
    """
    return f"Resultado: {parametro}"
```

O decorator extrai automaticamente:
- **Nome**: `minha_ferramenta` (nome da funcao)
- **Descricao**: primeira linha da docstring
- **Parametros**: da assinatura da funcao, convertidos em JSON Schema
- **Obrigatoriedade**: parametros sem valor default sao `required`

### Acessando o estado da sessao

Para acessar ou modificar o estado da sessao dentro de uma tool, use `RunContext`:

```python
from app.runtime import tool, RunContext

@tool
def salvar_dados(run_context: RunContext, nome: str, email: str = "") -> str:
    """Salva dados do cliente na sessao atual."""
    if "cliente" not in run_context.session_state:
        run_context.session_state["cliente"] = {}

    run_context.session_state["cliente"]["nome"] = nome
    if email:
        run_context.session_state["cliente"]["email"] = email

    return f"Dados salvos: nome={nome}"
```

O parametro `run_context` e **filtrado automaticamente** do schema JSON enviado ao LLM. O `ToolRegistry` o injeta no momento da execucao.

### Controlando o fluxo do agente

Duas excecoes permitem controlar o loop do agente de dentro de uma tool:

```python
from app.runtime import tool, RetryAgentRun, StopAgentRun

@tool
def ferramenta_com_validacao(cpf: str) -> str:
    """Valida e processa um CPF."""
    if len(cpf) != 11 or not cpf.isdigit():
        # Envia feedback ao LLM para corrigir e tentar novamente
        raise RetryAgentRun(
            "CPF invalido. O CPF deve conter exatamente 11 digitos numericos. "
            "Peca ao usuario para confirmar o CPF."
        )
    return f"CPF {cpf} validado com sucesso."


@tool
def encerrar_atendimento(motivo: str = "") -> str:
    """Encerra o atendimento imediatamente."""
    # Para o loop do agente; a mensagem e retornada como resposta final
    raise StopAgentRun(f"Atendimento encerrado. {motivo}")
```

| Excecao | Comportamento |
|---------|--------------|
| `RetryAgentRun(msg)` | A mensagem e adicionada como resultado da tool e o loop continua |
| `StopAgentRun(msg)` | O loop para imediatamente e a mensagem e a resposta final |

### Criando uma nova ferramenta

1. Crie o arquivo `app/tools/minha_tool.py`:

```python
"""Tool: minha_tool -- Descricao breve."""

from app.runtime import tool, RunContext, RetryAgentRun


@tool
def minha_tool(run_context: RunContext, parametro: str) -> str:
    """Descricao detalhada que o LLM vai ler para decidir quando usar.

    Args:
        parametro: Descricao do parametro.

    Returns:
        Resultado da operacao.
    """
    if not parametro:
        raise RetryAgentRun("O parametro e obrigatorio.")

    # Logica da ferramenta
    resultado = processar(parametro)

    # Salvar no estado da sessao se necessario
    run_context.session_state["ultimo_resultado"] = resultado

    return resultado
```

2. Registre no `app/tools/__init__.py`:

```python
from app.tools.minha_tool import minha_tool

__all__ = [
    # ... tools existentes ...
    "minha_tool",
]
```

3. Adicione ao registro em `app/agent.py`:

```python
from app.tools import (
    # ... imports existentes ...
    minha_tool,
)

def get_tools_registry() -> ToolRegistry:
    registry = ToolRegistry()
    all_tools = [
        # ... tools existentes ...
        minha_tool,
    ]
    for tool_def in all_tools:
        registry.register(tool_def)
    return registry
```

### Como o ToolRegistry funciona

O `ToolRegistry` em `app/runtime.py` gerencia o ciclo de vida das tools:

```python
from app.runtime import ToolRegistry

registry = ToolRegistry()

# Registrar uma tool (recebe um ToolDefinition retornado pelo @tool)
registry.register(minha_tool)

# Gerar definicoes OpenAI-compatible para litellm
definitions = registry.get_definitions()
# Retorna: [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]

# Executar uma tool (injeta RunContext automaticamente se necessario)
result = await registry.execute("minha_tool", {"parametro": "valor"}, run_context)
```

---

## Configuracao de Memoria

### Memoria de sessao (curto prazo)

Dados da sessao atual sao armazenados no `session_state` do `RunContext`. Tools como `salvar_dados_cliente` e `salvar_preferencias` persistem dados neste dicionario, que e mantido no Redis durante a sessao.

```python
# Configuracoes relevantes em .env
REDIS_URL=redis://localhost:6379/0
REDIS_SESSION_TTL=86400   # 24 horas
NUM_HISTORY_RUNS=2         # Turnos de historico enviados ao LLM
```

### Consolidacao de memoria (longo prazo)

O sistema em `app/memory.py` usa um LLM mais barato para consolidar o historico da conversa em fatos estruturados:

1. A cada mensagem, um contador `unconsolidated` e incrementado
2. Quando `unconsolidated >= MEMORY_WINDOW`, a consolidacao e disparada em background
3. Um LLM le o historico recente + fatos existentes e gera fatos atualizados
4. Os fatos sao armazenados no Redis (`memory:{cid}:facts`) e injetados no system prompt

```python
# Configuracoes em .env
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_WINDOW=20                              # Mensagens antes de consolidar
MEMORY_CONSOLIDATION_MODEL=claude-haiku-4-5-20251001  # Modelo barato para consolidacao
MEMORY_CONSOLIDATION_MAX_TOKENS=1024
```

Se `MEMORY_CONSOLIDATION_MODEL` estiver vazio, o modelo padrao (`DEFAULT_MODEL`) sera usado.

### Chaves Redis de memoria

| Chave | Conteudo |
|-------|----------|
| `memory:{cid}:facts` | Fatos consolidados (markdown) |
| `memory:{cid}:log` | Entradas de log de consolidacao (lista) |
| `memory:{cid}:unconsolidated` | Contador de mensagens nao consolidadas |
| `memory:{cid}:last_consolidated` | Indice da ultima mensagem consolidada |

---

## Construcao das Mensagens

A funcao `build_system_messages()` em `app/agent.py` monta o array de mensagens no formato LiteLLM/OpenAI:

```python
def build_system_messages(
    instructions: str,
    text_message: str,
    images: list[dict] | None = None,
    history: list[dict] | None = None,
) -> list[dict]:
    """Monta as mensagens para litellm.acompletion()."""
    messages = [
        {'role': 'system', 'content': instructions},
    ]

    # Historico de conversas anteriores
    if history:
        for msg in history:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if content and role in ('user', 'assistant'):
                messages.append({'role': role, 'content': content})

    # Mensagem atual (com suporte multimodal)
    if images:
        content_parts = [{'type': 'text', 'text': text_message}]
        content_parts.extend(images)
        messages.append({'role': 'user', 'content': content_parts})
    else:
        messages.append({'role': 'user', 'content': text_message})

    return messages
```

### Input Multimodal

O LiteLLM suporta envio de imagens no formato content parts da OpenAI:

```python
# Imagem via URL
images = [
    {
        "type": "image_url",
        "image_url": {"url": "https://exemplo.com/foto.jpg"},
    }
]

# Imagem via base64
images = [
    {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,iVBORw0KGgo..."},
    }
]

messages = build_system_messages(
    instructions="Voce e um assistente visual.",
    text_message="Descreva esta imagem.",
    images=images,
)
```

---

## O Agent Loop

O `run_agent_loop()` em `app/agent_loop.py` implementa o loop iterativo de tool-calling:

```python
from app.agent_loop import run_agent_loop, AgentResponse

response: AgentResponse = await run_agent_loop(
    messages=messages,          # Lista de mensagens (system + user)
    tools=registry,             # ToolRegistry com tools registradas
    run_context=run_context,    # RunContext com session_state
    model="anthropic/claude-sonnet-4-20250514",
    max_iterations=10,          # Maximo de iteracoes (settings.MAX_TURNS)
    temperature=0.1,
    max_tokens=2048,            # settings.MAX_OUTPUT_TOKENS
)

# AgentResponse contem:
response.content          # Texto da resposta final
response.messages         # Historico completo de mensagens
response.input_tokens     # Total de tokens de entrada
response.output_tokens    # Total de tokens de saida
response.tools_used       # Lista de nomes das tools chamadas
response.session_state    # Estado da sessao atualizado
```

### Comportamento do loop

1. Chama `litellm.acompletion()` com as mensagens e tools
2. Se a resposta contem `tool_calls`:
   - Adiciona a mensagem do assistente ao historico
   - Executa cada tool via `ToolRegistry.execute()`
   - Adiciona os resultados como mensagens `role: "tool"`
   - Repete o loop
3. Se a resposta nao contem `tool_calls`:
   - Retorna o `AgentResponse` com o conteudo final
4. Se atingir `max_iterations`:
   - Retorna uma mensagem informando o limite

---

## Parametros de Configuracao

### Variaveis de ambiente principais

```bash
# === Modelo ===
MODEL_PROVIDER=anthropic                  # anthropic | openai | vertexai
DEFAULT_MODEL=claude-sonnet-4-20250514    # ID do modelo (sem prefixo do provider)
ANTHROPIC_API_KEY=sk-ant-...              # Chave API Anthropic
OPENAI_API_KEY=sk-...                     # Chave API OpenAI
GOOGLE_CLOUD_PROJECT=meu-projeto          # Projeto GCP (Vertex AI)
GOOGLE_CLOUD_REGION=us-east5              # Regiao GCP (Vertex AI)

# === Comportamento do Agente ===
MAX_TURNS=10                              # Maximo de iteracoes do agent loop
MAX_OUTPUT_TOKENS=2048                    # Tokens maximos por chamada LLM
NUM_HISTORY_RUNS=2                        # Turnos de historico no contexto
TOOL_CALL_LIMIT=5                         # Limite de tool calls por turno
TOOL_OUTPUT_MAX_CHARS=500                 # Truncar output de tools acima deste limite
CACHE_SYSTEM_PROMPT=true                  # Cache do system prompt (Anthropic)

# === Memoria ===
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_WINDOW=20                          # Mensagens ate consolidar
MEMORY_CONSOLIDATION_MODEL=               # Modelo para consolidacao (vazio = DEFAULT_MODEL)
MEMORY_CONSOLIDATION_MAX_TOKENS=1024

# === Storage ===
REDIS_URL=redis://localhost:6379/0
REDIS_SESSION_TTL=86400                   # TTL da sessao (24h)

# === Prompt ===
AGENT_PROMPT_NAME=agent-instructions      # Nome do prompt no Langfuse
AGENT_PROMPT_LABEL=production             # Label do prompt
```

### Tabela completa de configuracao do agente

| Variavel | Tipo | Default | Descricao |
|----------|------|---------|-----------|
| `MODEL_PROVIDER` | `str` | `anthropic` | Provider do modelo |
| `DEFAULT_MODEL` | `str` | `gpt-5-mini` | ID do modelo padrao |
| `MAX_TURNS` | `int` | `10` | Iteracoes maximas do loop |
| `MAX_OUTPUT_TOKENS` | `int` | `2048` | Tokens maximos por resposta |
| `NUM_HISTORY_RUNS` | `int` | `2` | Turnos de historico no contexto |
| `TOOL_CALL_LIMIT` | `int` | `5` | Limite de tool calls |
| `TOOL_OUTPUT_MAX_CHARS` | `int` | `500` | Truncar output de tools |
| `CACHE_SYSTEM_PROMPT` | `bool` | `true` | Cache do system prompt |
| `REASONING_EFFORT` | `str` | `low` | Esforco de raciocinio |
| `MEMORY_CONSOLIDATION_ENABLED` | `bool` | `true` | Habilitar consolidacao |
| `MEMORY_WINDOW` | `int` | `20` | Mensagens ate consolidar |
| `MEMORY_CONSOLIDATION_MODEL` | `str` | `""` | Modelo para consolidacao |
| `MEMORY_CONSOLIDATION_MAX_TOKENS` | `int` | `1024` | Tokens para consolidacao |

---

## Personalizando o Comportamento

### Instrucoes do agente

As instrucoes do agente (system prompt) sao gerenciadas pelo `app/prompt_manager.py`, que busca o prompt no Langfuse ou usa o fallback configurado em `AGENT_INSTRUCTIONS_FALLBACK` no `app/config.py`.

Para alterar as instrucoes:

1. **Via Langfuse** (recomendado para producao): Edite o prompt pelo dashboard do Langfuse
2. **Via variavel de ambiente**: Altere `AGENT_INSTRUCTIONS_FALLBACK` no `.env`
3. **Via codigo**: Edite a constante `AGENT_INSTRUCTIONS_FALLBACK` em `app/config.py`

### Adicionando contexto automatico

O contexto da sessao (dados do cliente, preferencias) e injetado automaticamente no system prompt via tools de memoria:

```python
# As tools abaixo salvam dados no session_state:
salvar_dados_cliente(run_context, nome="Joao", convenio="OdontoPrev")
salvar_preferencias(run_context, chave="horario_preferido", valor="manha")

# Para visualizar o contexto acumulado:
ver_contexto_sessao(run_context)
```

O contexto e formatado pela funcao `formatar_contexto_completo()` e injetado nas instrucoes antes de cada chamada ao LLM.

---

## Imports de Referencia

Imports principais do runtime:

| Import | Descricao |
|--------|-----------|
| `from app.runtime import tool` | Decorator para criar tools |
| `from app.runtime import RunContext` | Contexto da sessao (session_state, user_id, etc.) |
| `from app.runtime import RetryAgentRun` | Excecao para feedback ao modelo |
| `from app.runtime import StopAgentRun` | Excecao para parar o loop |
| `from app.agent_loop import run_agent_loop` | Funcao principal do agent loop |

Modelos sao especificados como strings LiteLLM:

| Provider | Formato |
|----------|---------|
| Anthropic | `"anthropic/claude-sonnet-4-20250514"` |
| OpenAI | `"openai/gpt-5-mini"` |
| Vertex AI | `"vertex_ai/claude-sonnet-4@20250514"` |
| Google Gemini | `"gemini/gemini-1.5-flash"` |
| Ollama | `"ollama/llama3.2"` |
| AWS Bedrock | `"bedrock/anthropic.claude-3-sonnet..."` |

---

## Referencias

- [LiteLLM - Documentacao](https://docs.litellm.ai/)
- [LiteLLM - Providers Suportados](https://docs.litellm.ai/docs/providers)
- [OpenAI - Tool Calling](https://platform.openai.com/docs/guides/function-calling)
