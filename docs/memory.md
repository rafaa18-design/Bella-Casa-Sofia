# Memory (Consolidacao LLM-driven de Memoria de Longo Prazo)

O sistema de memoria utiliza consolidacao dirigida por LLM para manter fatos estruturados sobre o usuario/paciente ao longo de conversas longas. A consolidacao e feita por um modelo mais barato que resume periodicamente o historico de mensagens em fatos persistentes no Redis.

Implementacao: `app/memory.py`

---

## Conceitos

| Conceito | Descricao |
|----------|-----------|
| **Fatos consolidados** | Markdown estruturado com informacoes conhecidas sobre o usuario, armazenado em `memory:{cid}:facts` |
| **Log de consolidacao** | Entradas de resumo com timestamp, armazenadas em `memory:{cid}:log` |
| **Contador de nao-consolidados** | Contador incremental em `memory:{cid}:unconsolidated`, resetado apos cada consolidacao |
| **Janela de memoria** | Numero de mensagens (`MEMORY_WINDOW`) antes de disparar uma consolidacao |
| **Modelo de consolidacao** | LLM mais barato usado para sumarizar (configuravel via `MEMORY_CONSOLIDATION_MODEL`) |

---

## Arquitetura

```
Mensagem do usuario
       |
       v
increment_unconsolidated(cid)   ← +1 para user, +1 para assistant
       |
       v
should_consolidate(cid)?        ← unconsolidated >= MEMORY_WINDOW?
       |
      Sim
       |
       v
schedule_consolidation(cid)     ← asyncio.create_task (background)
       |
       v
consolidate(cid)
  1. Le fatos existentes do Redis (memory:{cid}:facts)
  2. Le historico recente (get_message_history)
  3. Envia para LLM de consolidacao com prompt de sistema
  4. LLM chama tool save_memory(history_entry, memory_update)
  5. Salva fatos atualizados no Redis
  6. Adiciona entrada ao log
  7. Reseta contador de nao-consolidados para 0
```

---

## Chaves Redis

Cada conversa (`cid` = conversation_id) possui as seguintes chaves:

| Chave Redis | Tipo | Descricao |
|-------------|------|-----------|
| `memory:{cid}:facts` | String | Markdown com todos os fatos conhecidos sobre o usuario |
| `memory:{cid}:log` | List | Entradas de historico com timestamp (resumos das consolidacoes) |
| `memory:{cid}:unconsolidated` | String (int) | Contador de mensagens desde a ultima consolidacao |
| `memory:{cid}:last_consolidated` | String (int) | Indice da ultima mensagem consolidada |

Todas as chaves possuem TTL configurado por `REDIS_SESSION_TTL` (padrao: 24h).

---

## API Publica (`app/memory.py`)

### `get_memory_context(cid) -> str`

Retorna os fatos consolidados em formato markdown para injecao no system prompt. Retorna string vazia se nao houver fatos ou se o Redis estiver indisponivel.

```python
from app.memory import get_memory_context

memory_context = await get_memory_context(conversation_id)
# Retorno exemplo:
# "## Dados Pessoais\n- Nome: Joao Pereira\n- Convenio: OdontoPrev\n\n## Preferencias\n- Horario: manha"
```

### `increment_unconsolidated(cid) -> int`

Incrementa o contador de mensagens nao-consolidadas. Chamado duas vezes por turno (uma para a mensagem do usuario, outra para a resposta do assistente).

```python
from app.memory import increment_unconsolidated

count = await increment_unconsolidated(conversation_id)
# count = 5 (por exemplo)
```

### `should_consolidate(cid) -> bool`

Verifica se o contador de nao-consolidados atingiu o limite (`MEMORY_WINDOW`). Retorna `True` quando `unconsolidated >= MEMORY_WINDOW`.

```python
from app.memory import should_consolidate

if await should_consolidate(conversation_id):
    # Hora de consolidar
    ...
```

### `consolidate(cid) -> None`

Executa a consolidacao LLM-driven:

1. Le os fatos existentes (`memory:{cid}:facts`)
2. Le o historico recente via `get_message_history(cid, limit=MEMORY_WINDOW * 2)`
3. Formata as mensagens e envia para o LLM de consolidacao com o prompt de sistema
4. O LLM chama a tool `save_memory` com `history_entry` (resumo de 2-5 frases) e `memory_update` (fatos atualizados em markdown)
5. Salva os resultados no Redis e reseta o contador

```python
from app.memory import consolidate

await consolidate(conversation_id)
```

### `schedule_consolidation(cid) -> None`

Agenda a consolidacao como tarefa de background via `asyncio.create_task`. Usa um lock por sessao para evitar consolidacoes concorrentes.

```python
from app.memory import schedule_consolidation

schedule_consolidation(conversation_id)
# A consolidacao roda em background, nao bloqueia a resposta
```

### `shutdown_consolidation(timeout) -> None`

Aguarda tarefas de consolidacao ativas durante o shutdown graceful. Cancela tarefas que nao completarem dentro do timeout.

---

## Fluxo no `main.py`

A integracao com o fluxo principal ocorre em `execute_agent()`:

```python
# 1. Obter contexto de memoria para injecao no prompt
memory_context = ''
if settings.MEMORY_CONSOLIDATION_ENABLED:
    memory_context = await get_memory_context(conversation_id)

# 2. Formatar contexto completo (memoria + session state)
full_context = formatar_contexto_completo(session_state, memory_context)

# 3. Compilar prompt com contexto injetado
instructions = compile_prompt(template, session_context=full_context)

# ... execucao do agente ...

# 4. Apos a resposta: incrementar contador e agendar consolidacao se necessario
if settings.MEMORY_CONSOLIDATION_ENABLED:
    await increment_unconsolidated(conversation_id)  # mensagem do usuario
    await increment_unconsolidated(conversation_id)  # resposta do assistente
    if await should_consolidate(conversation_id):
        schedule_consolidation(conversation_id)
```

---

## Prompt de Consolidacao

O LLM de consolidacao recebe um prompt de sistema especifico (`_CONSOLIDATION_SYSTEM_PROMPT`) que instrui a:

1. Resumir mensagens recentes em um `history_entry` (2-5 frases com timestamp)
2. Atualizar `memory_update` com TODOS os fatos conhecidos, mesclando novos com existentes
3. Remover informacoes desatualizadas ou contraditorias
4. Organizar fatos por categoria (ex: `## Dados Pessoais`, `## Preferencias`, `## Historico`)
5. Escrever no idioma da conversa (portugues)

O LLM usa uma tool forcada (`tool_choice`) chamada `save_memory`:

```python
_SAVE_MEMORY_TOOL = {
    'type': 'function',
    'function': {
        'name': 'save_memory',
        'parameters': {
            'type': 'object',
            'properties': {
                'history_entry': {
                    'type': 'string',
                    'description': 'Resumo de 2-5 frases com [YYYY-MM-DD HH:MM]'
                },
                'memory_update': {
                    'type': 'string',
                    'description': 'Markdown com TODOS os fatos conhecidos, atualizados'
                }
            },
            'required': ['history_entry', 'memory_update']
        }
    }
}
```

---

## Injecao no Prompt

Os fatos consolidados sao injetados no system prompt via `formatar_contexto_completo()` (em `app/tools/formatar_contexto.py`):

```
--- MEMORIA DE LONGO PRAZO ---
## Dados Pessoais
- Nome: Joao Pereira
- Convenio: OdontoPrev
- Telefone: (11) 98765-4321

## Preferencias
- Horario preferido: manha
- Dentista preferido: Dra. Maria Silva

## Historico
- Realizou limpeza em janeiro/2025
--- FIM DA MEMORIA ---
```

Essa secao aparece antes do contexto de sessao, garantindo que o agente tenha acesso a informacoes de longo prazo mesmo em conversas com historico de mensagens limitado.

---

## Configuracao

Variaveis de ambiente (em `.env` ou exportadas):

```bash
# Habilitar/desabilitar consolidacao
MEMORY_CONSOLIDATION_ENABLED=true

# Numero de mensagens antes de disparar consolidacao
MEMORY_WINDOW=20

# Modelo LLM para consolidacao (mais barato que o principal)
# Vazio = usa DEFAULT_MODEL
MEMORY_CONSOLIDATION_MODEL=claude-haiku-4-5-20251001

# Maximo de tokens para a resposta de consolidacao
MEMORY_CONSOLIDATION_MAX_TOKENS=1024

# TTL das chaves Redis (em segundos)
REDIS_SESSION_TTL=86400
```

---

## Concorrencia e Resiliencia

| Aspecto | Comportamento |
|---------|---------------|
| **Lock por sessao** | `asyncio.Lock` por `cid` evita consolidacoes simultaneas para a mesma conversa |
| **Background task** | Consolidacao roda em `asyncio.create_task`, nao bloqueia a resposta ao usuario |
| **Redis indisponivel** | Todas as funcoes retornam valores seguros (string vazia, 0, False) se o Redis estiver fora |
| **Falha do LLM** | Registra erro no log e na metrica `memory_consolidation_total{status="failed"}`, mas nao afeta a resposta |
| **JSON malformado** | Usa `json_repair` como fallback para parsing dos argumentos da tool |
| **Graceful shutdown** | `shutdown_consolidation()` aguarda tarefas ativas antes de encerrar |

---

## Metricas Prometheus

| Metrica | Descricao |
|---------|-----------|
| `memory_consolidation_total{status="scheduled"}` | Consolidacoes agendadas |
| `memory_consolidation_total{status="completed"}` | Consolidacoes concluidas com sucesso |
| `memory_consolidation_total{status="failed"}` | Consolidacoes que falharam |
| `memory_consolidation_duration_seconds` | Duracao da consolidacao (histogram) |

---

## Diferenca: Memoria vs. Session State

| Aspecto | Memoria Consolidada | Session State |
|---------|---------------------|---------------|
| **Arquivo** | `app/memory.py` | `app/storage.py` |
| **Chave Redis** | `memory:{cid}:facts` | `session:{cid}:state` |
| **Conteudo** | Fatos de longo prazo (markdown) | Dados estruturados da sessao (JSON) |
| **Atualizacao** | Periodica (a cada MEMORY_WINDOW mensagens) | Imediata (via tools do agente) |
| **Mecanismo** | LLM consolida historico | Tools gravam diretamente |
| **Proposito** | Reter informacoes entre muitos turnos | Dados operacionais da sessao atual |
| **Injecao** | `--- MEMORIA DE LONGO PRAZO ---` | `--- CONTEXTO DA SESSAO ---` |

Ambos sao combinados por `formatar_contexto_completo()` e injetados no system prompt.

---

## Boas Praticas

| Pratica | Descricao |
|---------|-----------|
| **Use modelo barato** | Configure `MEMORY_CONSOLIDATION_MODEL` com um modelo economico (ex: claude-haiku) |
| **Ajuste MEMORY_WINDOW** | Valores menores consolidam mais frequentemente (mais custo, menos perda). Valores maiores economizam chamadas LLM |
| **Monitore metricas** | Acompanhe `memory_consolidation_total` para detectar falhas |
| **Combine com session state** | Memoria de longo prazo complementa o session state — use ambos |
| **Nao dependa exclusivamente** | A consolidacao e assincrona e pode falhar. O session state e mais confiavel para dados criticos |
