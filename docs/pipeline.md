# Pipeline Multi-Estágio

Guia para implementar uma arquitetura de pipeline com estágios separados quando o agente monolítico não é suficiente.

---

## Quando Usar Pipeline vs Monolítico

### Agente Monolítico (padrão do template)

Um único LLM recebe o prompt, as tools e a mensagem — decide sozinho o que fazer.

**Use quando:**
- Até ~10 tools
- Fluxo conversacional simples
- Latência é prioridade (1 chamada LLM + tool calls)
- Custo por requisição não é crítico

**Limitações:**
- O LLM vê todas as tools de uma vez (mais tokens de input)
- Pode chamar tools desnecessariamente ou em loop
- O prompt precisa cobrir todos os cenários em um bloco único
- Difícil debugar "por que chamou essa tool?"

### Pipeline Multi-Estágio

Separa o processamento em estágios especializados, cada um com responsabilidade distinta.

**Use quando:**
- Muitas tools (15+) — o LLM se confunde com schemas grandes
- O custo de tokens é uma preocupação (Intent Agent usa modelo barato)
- Precisa de determinismo na execução de tools (sem alucinações)
- Quer debugabilidade por estágio (métricas separadas)
- O prompt precisa mudar dinamicamente conforme o estágio da conversa
- O domínio tem fluxos complexos (coleta de dados → validação → ação → confirmação)

---

## Arquitetura: 3 Estágios

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Stage 1        │     │  Stage 2        │     │  Stage 3        │
│  Intent Agent   │────▶│  Tool Executor  │────▶│  Writer Agent   │
│  (LLM barato)   │     │  (sem LLM)      │     │  (LLM principal)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
     │                       │                       │
     ▼                       ▼                       ▼
 IntentResult           ExecutorResult          Resposta final
 - stage                - tools_executed        (texto para o
 - tool_calls           - session_state           usuário)
 - needs_info           - state_updated
 - reasoning
```

| Estágio | O que faz | LLM | Custo |
|---------|-----------|-----|-------|
| **Intent Agent** | Classifica intenção, planeja tool calls | Modelo barato (gpt-5-nano) | Baixo |
| **Tool Executor** | Executa tools planejadas | Nenhum | Zero |
| **Writer Agent** | Gera resposta final com prompt dinâmico | Modelo principal | Normal |

### Por que 3 estágios?

1. **Custo otimizado**: O Intent Agent usa modelo 5-10x mais barato. Só o Writer usa o modelo principal.
2. **Determinismo**: O Tool Executor é puro código — sem alucinações de LLM decidindo argumentos errados.
3. **Debugabilidade**: Cada estágio tem latência e tokens independentes. Sabe exatamente onde o tempo foi gasto.
4. **Prompt dinâmico**: O Writer recebe instruções específicas para cada estágio da conversa (saudação vs coleta vs ação).

---

## Implementação

### Estrutura de Arquivos

```
app/pipeline/
├── __init__.py          # Exports (run_pipeline, models)
├── models.py            # ConversationStage, IntentResult, ExecutorResult, PipelineResult
├── stages.py            # Prompts fixos + build_writer_prompt()
├── intent_agent.py      # Stage 1: classificação de intenção (litellm)
├── tool_executor.py     # Stage 2: execução de tools (sem LLM)
├── writer_agent.py      # Stage 3: geração de resposta (litellm)
└── orchestrator.py      # Coordena os 3 estágios
```

### Configuração

```bash
# app/config.py — adicionar na classe Settings:
PIPELINE_ENABLED: bool = True
INTENT_MODEL: str = 'gpt-5-nano'    # Modelo barato para classificação
WRITER_MODEL: str = ''               # Vazio = usa DEFAULT_MODEL
```

---

## Stage 1: Intent Agent

Classifica a intenção do usuário e planeja quais tools executar. Usa **structured output** (JSON mode) com um modelo barato.

### Models

```python
# app/pipeline/models.py

from enum import Enum
from pydantic import BaseModel, Field

class ConversationStage(str, Enum):
    greeting = 'greeting'       # Primeira interação
    collecting = 'collecting'   # Coletando dados que faltam
    action = 'action'           # Executando ação (agendar, cancelar)
    info = 'info'               # Respondendo pergunta informativa
    farewell = 'farewell'       # Despedida

class ToolCallRequest(BaseModel):
    tool_name: str = Field(..., description='Nome da tool a executar')
    arguments_json: str = Field(..., description='JSON string dos argumentos')

class IntentResult(BaseModel):
    stage: ConversationStage
    tool_calls: list[ToolCallRequest] = Field(..., description='Tools a executar')
    needs_info_from_user: str = Field(..., description='Dado que falta')
    reasoning: str = Field(..., description='Justificativa da decisão')
```

### Catálogo de Tools (compacto)

Em vez de enviar os JSON schemas completos das tools (que gastam muitos tokens), o Intent Agent recebe um catálogo compacto:

```python
TOOL_CATALOG = """FERRAMENTAS DISPONÍVEIS:
- verificar_cliente(): Verifica se o canal pertence a paciente cadastrado.
- listar_servicos(): Lista serviços com preços e duração.
- verificar_disponibilidade(data, dentista?): Horários disponíveis.
- agendar_consulta(paciente_nome, data, horario, servico, dentista_id): Agenda consulta.
- salvar_dados_cliente(nome, telefone?, email?, convenio?): Salva dados do cliente.
"""
```

Isso reduz o input de ~2000 tokens (schemas JSON) para ~300 tokens (catálogo texto).

### Implementação com LiteLLM

```python
# app/pipeline/intent_agent.py

import json
import litellm
from app.agent import get_litellm_model
from app.config import settings
from app.pipeline.models import IntentResult, ConversationStage

async def run_intent_agent(
    user_message: str,
    session_state: dict,
    history_summary: str = '',
    model_id: str | None = None,
) -> tuple[IntentResult, float, int, int, str]:

    intent_model_id = model_id or settings.INTENT_MODEL
    model = get_litellm_model(intent_model_id)

    # Montar contexto compacto
    context_parts = []
    if session_state:
        cliente = session_state.get('cliente', {})
        if cliente:
            context_parts.append(f"Cliente: {', '.join(f'{k}={v}' for k, v in cliente.items() if v)}")
        else:
            context_parts.append('ESTADO: sessão nova')
    if history_summary:
        context_parts.append(f'HISTÓRICO:\n{history_summary}')

    context_text = '\n'.join(context_parts)
    full_message = f'{context_text}\n\nMENSAGEM: {user_message}'

    start = time.perf_counter()
    response = await litellm.acompletion(
        model=model,
        messages=[
            {'role': 'system', 'content': INTENT_SYSTEM_PROMPT},
            {'role': 'user', 'content': full_message},
        ],
        response_format=IntentResult,  # Structured output
        temperature=0.0,
        max_tokens=256,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    # Parse structured output
    content = response.choices[0].message.content
    intent_result = IntentResult.model_validate_json(content)

    # Tokens
    usage = response.usage
    input_tokens = usage.prompt_tokens or 0
    output_tokens = usage.completion_tokens or 0

    return intent_result, latency_ms, input_tokens, output_tokens, intent_model_id
```

**Pontos-chave:**
- `response_format=IntentResult` — litellm envia o schema Pydantic como `response_format` para structured output
- `temperature=0.0` — classificação deve ser determinística
- `max_tokens=256` — output é pequeno (JSON estruturado), economia de tokens
- Modelo barato (`gpt-5-nano`) — 5-10x mais barato que o principal

---

## Stage 2: Tool Executor

Puramente determinístico. Nenhum LLM envolvido. Executa as tools planejadas pelo Intent Agent.

```python
# app/pipeline/tool_executor.py

import json
import inspect
from app.runtime import RunContext
from app.tools import (
    agendar_consulta, listar_servicos, verificar_cliente, # ...
)
from app.pipeline.models import ExecutorResult, IntentResult, ToolExecutionResult

# Registry: nome → ToolDefinition (do @tool decorator)
TOOL_REGISTRY = {
    'verificar_cliente': verificar_cliente,
    'listar_servicos': listar_servicos,
    # ... todas as tools
}

async def execute_tools(
    intent: IntentResult,
    session_id: str,
    session_state: dict,
) -> tuple[ExecutorResult, float]:

    if not intent.tool_calls:
        return ExecutorResult(session_state=session_state), 0.0

    run_context = RunContext(session_state=session_state, session_id=session_id)
    results = []

    for tool_call in intent.tool_calls:
        tool_def = TOOL_REGISTRY.get(tool_call.tool_name)
        if tool_def is None:
            results.append(ToolExecutionResult(
                tool_name=tool_call.tool_name, success=False,
                error=f'Tool not found: {tool_call.tool_name}',
            ))
            continue

        try:
            args = json.loads(tool_call.arguments_json) if tool_call.arguments_json else {}

            # Injetar run_context se a tool espera
            fn = tool_def.func
            sig = inspect.signature(fn)
            if 'run_context' in sig.parameters:
                args['run_context'] = run_context

            result = fn(**args)
            if inspect.isawaitable(result):
                result = await result

            results.append(ToolExecutionResult(
                tool_name=tool_call.tool_name, success=True, result=result,
            ))
        except Exception as e:
            results.append(ToolExecutionResult(
                tool_name=tool_call.tool_name, success=False, error=str(e),
            ))

    return ExecutorResult(
        tools_executed=results,
        session_state=run_context.session_state,
        state_updated=run_context.session_state != session_state,
    ), latency_ms
```

**Por que sequencial?** As tools podem mutar `session_state`. Se `salvar_dados_cliente` roda junto com `agendar_consulta`, o agendamento pode não ver os dados salvos. Ordem importa.

---

## Stage 3: Writer Agent

Gera a resposta final usando prompt dinâmico de 3 partes. Zero tools — apenas geração de texto.

```python
# app/pipeline/writer_agent.py

import litellm
from app.agent import get_litellm_model
from app.config import settings
from app.pipeline.models import ConversationStage, ExecutorResult
from app.pipeline.stages import build_writer_prompt

async def run_writer_agent(
    user_message: str,
    stage: ConversationStage,
    executor_result: ExecutorResult,
    history_summary: str = '',
    model_id: str | None = None,
) -> tuple[str, float, int, int, str, str]:

    writer_model_id = model_id or settings.WRITER_MODEL or settings.DEFAULT_MODEL
    model = get_litellm_model(writer_model_id)

    # Prompt dinâmico de 3 partes
    state_context = formatar_contexto_state(executor_result.session_state)
    final_prompt = build_writer_prompt(stage, state_context)

    # Mensagem com resultados das tools
    message_parts = []
    if history_summary:
        message_parts.append(f'HISTÓRICO:\n{history_summary}')
    if executor_result.tools_executed:
        message_parts.append(_format_tool_results(executor_result.tools_executed))
    message_parts.append(f'MENSAGEM DO PACIENTE:\n{user_message}')

    start = time.perf_counter()
    response = await litellm.acompletion(
        model=model,
        messages=[
            {'role': 'system', 'content': final_prompt},
            {'role': 'user', 'content': '\n\n'.join(message_parts)},
        ],
        temperature=0.3,
        max_tokens=1024,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    response_text = response.choices[0].message.content or ''
    return response_text, latency_ms, input_tokens, output_tokens, writer_model_id, final_prompt
```

---

## Prompt Dinâmico de 3 Partes

O poder do pipeline está no prompt dinâmico do Writer. Em vez de um prompt monolítico que tenta cobrir todos os cenários, o Writer recebe instruções específicas para o estágio detectado.

```
┌────────────────────────────────────────────┐
│  Parte A — Identidade (FIXA)               │
│  Quem é o agente, regras gerais, estilo    │
├────────────────────────────────────────────┤
│  Parte B — Contexto da Sessão (DINÂMICO)   │
│  Dados do cliente, preferências coletadas  │
├────────────────────────────────────────────┤
│  Parte C — Estágio (DINÂMICO)              │
│  Comportamento específico para este turno  │
└────────────────────────────────────────────┘
```

### Parte A: Identidade (fixa)

Igual para toda a conversa. Define quem é o agente, idioma, estilo, limitações.

```python
FIXED_IDENTITY = (
    'Você é a Ana, assistente virtual da Clínica Sorriso.\n\n'
    'IDIOMA: Sempre pt-BR.\n'
    'ESTILO: 1-2 perguntas por mensagem, breve e direto.\n'
    'DADOS: Nunca invente dados. Se não sabe, pergunte.\n'
    'LIMITAÇÕES: Não pode enviar SMS, email, WhatsApp ou notificações.\n'
)
```

### Parte B: Contexto da Sessão (dinâmico)

Gerado por `formatar_contexto_state()`. Muda conforme tools salvam dados:

```
--- CONTEXTO DA SESSÃO ---
DADOS DO CLIENTE: nome: Carlos Eduardo | telefone: 11 99999-0000
PREFERÊNCIAS: dentista_preferido: Dra. Maria | alergia: latex
--- FIM DO CONTEXTO ---
```

### Parte C: Estágio (dinâmico)

Cada `ConversationStage` tem um prompt comportamental:

```python
# app/pipeline/stages.py

STAGE_PROMPTS = {
    ConversationStage.greeting: (
        'COMPORTAMENTO NESTE MOMENTO:\n'
        '- Cumprimente pelo nome se identificado no contexto\n'
        '- Se paciente novo, informe avaliação gratuita\n'
        '- Pergunte como pode ajudar\n'
    ),
    ConversationStage.collecting: (
        'COMPORTAMENTO NESTE MOMENTO:\n'
        '- Peça UM dado por vez\n'
        '- Use dados do contexto para não repetir perguntas\n'
        '- Confirme dados recebidos antes de avançar\n'
    ),
    ConversationStage.action: (
        'COMPORTAMENTO NESTE MOMENTO:\n'
        '- Apresente o resultado da ação executada\n'
        '- Se agendou: confirme data, horário, dentista, serviço\n'
        '- Pergunte se pode ajudar com mais algo\n'
    ),
    ConversationStage.info: (
        'COMPORTAMENTO NESTE MOMENTO:\n'
        '- Responda com dados das ferramentas (preços, horários)\n'
        '- Seja objetivo e completo\n'
    ),
    ConversationStage.farewell: (
        'COMPORTAMENTO NESTE MOMENTO:\n'
        '- Encerre com resumo do atendimento\n'
        '- Em emergência: (11) 3000-1234\n'
    ),
}

def build_writer_prompt(stage: ConversationStage, state_context: str) -> str:
    parts = [FIXED_IDENTITY]
    if state_context:
        parts.append(state_context)
    stage_prompt = STAGE_PROMPTS.get(stage, '')
    if stage_prompt:
        parts.append(stage_prompt)
    return '\n'.join(parts)
```

### Vantagem sobre prompt monolítico

| Prompt Monolítico | Prompt Dinâmico |
|-------------------|-----------------|
| ~3000 tokens (cobre tudo) | ~800 tokens (só o relevante) |
| LLM precisa "escolher" qual seção seguir | LLM recebe só a seção do estágio atual |
| Fácil de violar regras de outros estágios | Cada estágio é isolado |
| Difícil de debugar | Sabe exatamente qual prompt foi usado |

---

## Orchestrator

Coordena os 3 estágios e retorna o resultado consolidado:

```python
# app/pipeline/orchestrator.py

async def run_pipeline(
    user_message: str,
    conversation_id: str,
    session_state: dict,
    intent_model: str | None = None,
    writer_model: str | None = None,
) -> PipelineResult:

    # Histórico recente (últimas 6 mensagens)
    history = await get_message_history(conversation_id, limit=6)
    history_summary = '\n'.join(
        f"{'Paciente' if m['role'] == 'user' else 'Ana'}: {m['content'][:200]}"
        for m in history[-6:]
    ) if history else ''

    # Stage 1: Intent
    intent_result, intent_latency, intent_in, intent_out, intent_model_used = (
        await run_intent_agent(user_message, session_state, history_summary, intent_model)
    )

    # Stage 2: Executor
    executor_result, executor_latency = await execute_tools(
        intent_result, conversation_id, session_state,
    )

    # Stage 3: Writer
    response_text, writer_latency, writer_in, writer_out, writer_model_used, writer_prompt = (
        await run_writer_agent(user_message, intent_result.stage, executor_result, history_summary, writer_model)
    )

    return PipelineResult(
        message=response_text,
        stage=intent_result.stage,
        actions=executor_result.tools_executed,
        session_state=executor_result.session_state,
        intent_latency_ms=intent_latency,
        executor_latency_ms=executor_latency,
        writer_latency_ms=writer_latency,
        # ... tokens, prompts, debug info
    )
```

---

## Integração com o Template

### Feature Flag em `execute_agent()`

Na rota `/run` (em `app/routes/agentbench.py`), adicione o roteamento:

```python
if settings.PIPELINE_ENABLED:
    from app.pipeline import run_pipeline

    pipeline_result = await run_pipeline(
        user_message=text_message,
        conversation_id=conversation_id,
        session_state=session_state,
        writer_model=request.model,
    )
    response_text = pipeline_result.message
    actions = [
        ActionTaken(tool=t.tool_name, success=t.success, error=t.error)
        for t in pipeline_result.actions
    ]
    session_state = pipeline_result.session_state
else:
    # Modo monolítico (padrão do template)
    response = await run_agent_loop(messages, tools, run_context, model, ...)
    response_text = response.content
```

### Debug Trajectory

No `/run_debug`, converta `PipelineResult` em trajectory com 3 stages:

```json
{
  "trajectory": [
    {
      "stage": "intent_agent",
      "model": "gpt-5-nano",
      "latency_ms": 120,
      "result": {"stage": "greeting", "tool_calls": [{"tool_name": "verificar_cliente"}]}
    },
    {
      "stage": "tool_executor",
      "latency_ms": 45,
      "tools_executed": [{"tool_name": "verificar_cliente", "success": true}]
    },
    {
      "stage": "writer_agent",
      "model": "gpt-5-mini",
      "latency_ms": 890,
      "prompt": "Você é a Ana... COMPORTAMENTO: Cumprimente pelo nome..."
    }
  ]
}
```

---

## Adicionando Estágios

### Novo ConversationStage

1. Adicione ao enum em `models.py`:
```python
class ConversationStage(str, Enum):
    # ... existentes ...
    confirmation = 'confirmation'   # Confirmando dados antes de agir
```

2. Adicione o prompt em `stages.py`:
```python
STAGE_PROMPTS[ConversationStage.confirmation] = (
    'COMPORTAMENTO NESTE MOMENTO:\n'
    '- Liste todos os dados coletados para o paciente confirmar\n'
    '- Pergunte "Está tudo correto?" antes de prosseguir\n'
    '- Se o paciente corrigir algo, atualize e confirme novamente\n'
)
```

3. Atualize o `INTENT_SYSTEM_PROMPT` em `intent_agent.py`:
```python
'- confirmation: confirmando dados antes de executar ação\n'
```

### Nova Tool

1. Crie a tool em `app/tools/` com `@tool` do `app.runtime`
2. Exporte em `app/tools/__init__.py`
3. Registre em `app/agent.py` (monolítico) E em `tool_executor.py` (pipeline)
4. Adicione ao `TOOL_CATALOG` em `intent_agent.py`:
```python
'- minha_tool(param1, param2?): Descrição breve.\n'
```

---

## Comparação de Performance

Exemplo real com 10 mensagens de conversa odontológica:

| Métrica | Monolítico | Pipeline |
|---------|-----------|----------|
| **Latência média** | ~26s | ~18s (intent=2s + exec=0.05s + writer=16s) |
| **Tokens input/msg** | ~3000 (prompt completo + tools schemas) | ~1500 (intent=500 + writer=1000) |
| **Custo estimado** | 1x | ~0.6x (intent usa modelo 10x mais barato) |
| **Tool calls corretas** | ~85% | ~95% (intent planeja, executor valida) |
| **Debugabilidade** | Baixa (1 bloco) | Alta (3 estágios com métricas) |

O pipeline é mais lento na latência total (2 chamadas LLM vs 1), mas:
- Reduz custo por usar modelo barato no Stage 1
- Reduz tokens por usar catálogo compacto + prompt dinâmico
- Aumenta precisão de tool calls
- Permite debugging granular

---

## Quando NÃO Usar Pipeline

- **Chatbot simples** (FAQ, sem tools) — overhead desnecessário
- **Poucas tools** (<5) — o monolítico funciona bem
- **Latência crítica** — pipeline adiciona 1 chamada LLM extra
- **Prototipação rápida** — o monolítico é mais simples de configurar
- **Streaming obrigatório** — pipeline não suporta streaming nativamente (precisa esperar os 3 estágios)

O template usa o modo monolítico por padrão (`PIPELINE_ENABLED=false`). Ative o pipeline quando a complexidade justificar.
