# Sofia — Bella Casa IA Leads

Agente de qualificação de leads da **Bella Casa** (móveis planejados, Santo Antônio de Jesus/BA), publicado no WhatsApp via **UazAPI** e na web via app **Next.js (`chat/`)**. A persona é a **Sofia**, vendedora digital que triagia o cliente, registra o lead em Postgres, distribui para a vendedora humana via round-robin e agenda visita à loja com lembrete automático.

Base técnica: FastAPI + LiteLLM + agent loop próprio (padrão AgentBench da Asani). Deploy em **Railway** (Nixpacks) com Postgres + Redis. Para o template genérico que originou este projeto, veja [docs/](./docs/).

## Arquitetura em uma página

```
WhatsApp ──► UazAPI ──► POST /webhook ──► _process_message
                                           │
                                           ├─ load_conversation_history (Postgres)
                                           ├─ get_agent_instructions (prompts/sofia.md, cache Redis)
                                           ├─ run_agent_loop (litellm + tools)
                                           │     verificar_cliente → rotear_cidade → verificar_horario
                                           │     → registrar_lead → distribuir_vendedora
                                           │     → agendar_visita → transferir_vendedora (StopAgentRun)
                                           ├─ _clean_response (sem markdown/emoji, 1 pergunta)
                                           ├─ save_conversation_message (Postgres)
                                           └─ _send_whatsapp (UazAPI /send/text)

Chat web (chat/) ──► /api/[...path] (proxy) ──► mesmo /webhook
                                              (conversation_id UUID → bypass allowlist)

APScheduler (lifespan startup)
   ├─ 21h30 UTC  → send_visit_reminders    (véspera da visita)
   └─ 13h00 UTC  → send_cold_lead_followups (leads "novo" >5 dias → "frio")
```

Tudo que toca o lead em si vive em `app/tools/bella_casa.py`. As tools chamam de volta o próprio FastAPI em `/api/firebase/*` — o prefixo é histórico (era Firestore) e foi mantido após a migração para Postgres para não quebrar o tooling. **Não há mais Firebase em runtime** (`firebase-admin` e `google-cloud-firestore` foram removidos em `3a9fa2d`).

## Estrutura

```
bella-casa-ia-leads/
├── app/
│   ├── main.py              # FastAPI lifespan: redis, prompt cache, scheduler
│   ├── agent.py             # litellm wrapper + run_agent_loop + tools registry da Sofia
│   ├── runtime.py           # @tool, RunContext, ToolRegistry, RetryAgentRun/StopAgentRun
│   ├── scheduler.py         # APScheduler: visit reminders + cold-lead follow-up
│   ├── prompt_manager.py    # Carrega prompts/sofia.md (com cache Redis + fallback)
│   ├── memory.py            # Consolidação LLM-driven (haiku) — herdado do template
│   ├── middleware.py        # RequestID, JWT, security headers
│   ├── db/                  # SQLAlchemy async — modela o schema Prisma do dashboard
│   ├── routes/
│   │   ├── webhook.py       # UazAPI → Sofia (handoff Redis 24h, inactivity monitor, anti-grupo)
│   │   ├── firebase_api.py  # /api/firebase/* (leads, sellers, conversations) — Postgres
│   │   ├── reminders.py     # /reminders/status, /reminders/run — debug do scheduler
│   │   ├── agentbench.py    # /metadata, /run, /run_debug (compat AgentBench)
│   │   ├── auth.py, prompts.py, system.py
│   ├── tools/
│   │   ├── bella_casa.py    # ÚNICO arquivo de tools usado em produção
│   │   ├── formatar_contexto.py
│   │   └── pacientes.py, consultas.py, catalogo.py, sessao.py, _mock_data.py
│   │                        # ↑ herdados do template "clínica" — NÃO registrados em agent.py
│   └── audit.py, metrics.py, observability.py, rate_limiter.py, resilience.py
├── prompts/
│   ├── sofia.md             # Prompt de produção (carregado via prompt_manager)
│   └── valentina.md         # Prompt legado (nome antigo da persona)
├── chat/                    # Next.js 16 + React 19 — interface web da Sofia
│   └── src/app/
│       ├── page.tsx                 # UI do chat
│       └── api/[...path]/route.ts   # Proxy para o backend FastAPI
├── alembic/                 # Migrations Postgres (schema espelha o dashboard Prisma)
├── scripts/hash_password.py
├── railway.toml             # Deploy: nixpacks + uvicorn + /health
├── Procfile, Dockerfile, docker-compose.{yml,dev.yml}
└── tests/
```

> **Tools registradas hoje** (`app/agent.py:get_tools_registry`): apenas as 7 da Sofia em `bella_casa.py`. Os arquivos `pacientes.py`, `consultas.py`, `catalogo.py`, `sessao.py`, `_mock_data.py` ficaram do template odontológico e **não são usados** — não consulte como referência de produção.

## Fluxo da Sofia (resumo do prompt + tools)

1. **Mensagem 1** — chama `verificar_cliente` (lookup por telefone em `/api/firebase/leads/by-phone/{phone}`). Se recorrente, cumprimenta pelo nome, atribui à vendedora original e já vai pro handoff.
2. **Pergunta o nome** (apenas o primeiro, gênero neutro — ver `prompts/sofia.md`).
3. **Pergunta a cidade** → `rotear_cidade`. Lista `MATRIZ_CITIES` define quem é da praça (Santo Antônio de Jesus + microrregião). Matriz ⇒ `invite_visit: true`.
4. **Qualifica produto, prazo (`imediato`/`30_dias`/`pesquisando``) e propósito (`reforma`/`casa_nova`/`troca`)**.
5. **`verificar_horario`** (timezone `America/Bahia`, horários de loja em `BUSINESS_HOURS`) — define saudação e se a loja está aberta.
6. **`registrar_lead`** → POST `/api/firebase/leads` → grava na tabela `leads` (Postgres) com `status=novo` e `routing_type` calculado.
7. **`distribuir_vendedora`** → round-robin via `RoundRobinControl` (ou força um `sellerId` específico se recorrente).
8. **`agendar_visita`** (opcional, só matriz) — parser tolerante: aceita "amanhã"/"hoje"/"segunda"/"DD/MM"/`HH:MM`/`HHhMM`. Valida horário comercial e cria `Reminder` para véspera 18h30 BRT.
9. **`transferir_vendedora`** → `StopAgentRun` com JSON `{handoff, seller_name, farewell, ...}`. O webhook envia o `farewell` ao cliente, marca `handoff:{phone}` no Redis (TTL 24h) e a partir daí responde com mensagem de espera padrão até o TTL expirar.

## Comandos rápidos

```bash
uv sync                                  # Instalar deps
uv run uvicorn app.main:app --reload     # API local (porta 8000)
uv run alembic upgrade head              # Aplicar migrations
uv run pytest                            # Testes
uv run scripts/hash_password.py          # Bcrypt para AUTH_USERS

cd chat && npm install && npm run dev    # UI web em http://localhost:3000

docker compose -f docker-compose.dev.yml up   # Postgres + Redis locais
make dev                                       # Atalho do Makefile

# Debug do scheduler
curl localhost:8000/reminders/status
curl -X POST localhost:8000/reminders/run/visit_reminders

# Forçar reload do prompt sem reiniciar
curl -X POST localhost:8000/prompts/refresh
```

## Variáveis de ambiente essenciais

```bash
# Identidade
MODULE_ID=bella-casa-sofia
AGENT_NAME=sofia
AGENT_PROMPT_NAME=sofia          # Carrega prompts/sofia.md

# Modelo (default atual: gpt-5-mini via OpenAI)
MODEL_PROVIDER=openai
DEFAULT_MODEL=gpt-5-mini
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...            # opcional, se rodar Claude
GEMINI_API_KEY=...               # opcional, transcrição de áudio

# Storage
POSTGRES_URL=postgresql+psycopg://...    # Railway injeta DATABASE_URL — exporte como POSTGRES_URL
REDIS_URL=redis://...

# WhatsApp (UazAPI)
UAZAPI_URL=https://free.uazapi.com
UAZAPI_TOKEN=...                  # Header: token (não Bearer)

# API interna /api/firebase/*
FIREBASE_ADMIN_TOKEN=...          # Bearer compartilhado entre Sofia e dashboard
FIREBASE_BASE_URL=                # Vazio = usa http://localhost:$PORT/api/firebase

# Allowlist (testes controlados; UUIDs e IDs não-numéricos passam direto)
PHONE_ALLOWLIST=["5575999999999"]

# Auth/JWT (obrigatório em prod)
AUTH_ENABLED=true
JWT_SECRET=<32+ chars>
AUTH_USERS={"admin":"$2b$12$..."}

# Observability
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
METRICS_ENABLED=true
```

## Persistência (Postgres)

Schema espelha o **Prisma do dashboard** (`bella-casa-dashboard/prisma/schema.prisma` — fonte de verdade). Os enums (`RoutingType`, `PurchasePurpose`, `PurchaseTimeline`, `LeadStatus`, `Language`, `ConversationStage`) são criados pelo Prisma; o SQLAlchemy usa `create_type=False`. Tabelas: `sellers`, `leads`, `conversations`, `messages`, `reminders`, `round_robin_control`.

**Não edite o schema só por aqui** — alinhe com o dashboard antes de qualquer migration.

## Endpoints

| Rota | Método | Descrição |
|------|--------|-----------|
| `/webhook` | POST | Entrada do UazAPI (também aceita `/webhook/messages/{type}`) |
| `/api/firebase/leads` etc. | GET/POST | API interna usada pelas tools e pelo dashboard |
| `/reminders/status`, `/reminders/run/{job}` | GET/POST | Debug do APScheduler |
| `/prompts/{current,refresh,webhook}` | GET/POST | Gestão do prompt (Langfuse opcional) |
| `/auth/login`, `/auth/token` | POST | JWT (login devolve `access_token`) |
| `/metadata`, `/run`, `/run_debug` | — | Compatibilidade AgentBench |
| `/health`, `/metrics` | GET | Healthcheck (Railway) + Prometheus |

## Deploy (Railway)

- Builder: **nixpacks** (`railway.toml`) com Python 3.12 + `uv`.
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, healthcheck `/health`.
- Serviços: app (este repo) + Postgres + Redis. O webhook do UazAPI deve apontar para `https://<app>.railway.app/webhook`.
- Há um workflow legado `.github/workflows/` para **Cloud Run** (`bella-casa-asani`) — Railway é o ambiente de produção atual; Cloud Run continua disponível como alternativa.

## Padrões e gotchas

- **Mensagens ao cliente** passam por `_clean_response` (`app/routes/webhook.py`): zero markdown, zero emoji, máx. 1 pergunta. Não tente sofisticar a formatação no prompt — o pós-processamento corta.
- **Pensamento interno** (Gemini thinking, `(Pensamento):`, `<thinking>`) é removido por `_strip_internal_thinking`. Se a Sofia mudar de modelo, valide que esse filtro continua cobrindo o formato novo.
- **Handoff** é persistente: marcado em memória, no `session_state` e em `handoff:{phone}` no Redis (TTL 24h). Para "soltar" um número antes do TTL, `DEL handoff:<phone>` no Redis.
- **Grupos do WhatsApp são ignorados** (`is_group` → `ignored_group`). DM-only por design.
- **Allowlist** (`PHONE_ALLOWLIST`): só restringe `conversation_id` puramente numérico. UUIDs/IDs do chat web passam direto (commit `95daf5a`/`6447d26`).
- **Cache do prompt** é zerado no `lifespan` startup para sempre carregar a versão mais recente de `prompts/sofia.md` (commit `d9b5e5a`). Edite o arquivo, faça redeploy — e pronto.
- **Tools**: erros recuperáveis ⇒ `raise RetryAgentRun(msg)` (o LLM vê o feedback e tenta de novo). Terminar a conversa ⇒ `raise StopAgentRun(json)`.
- **`MATRIZ_CITIES` e `BUSINESS_HOURS`** vivem hardcoded em `app/tools/bella_casa.py`. Mudou loja/cidade? Edite aqui.

## Tarefas comuns

| Quero… | Onde mexer |
|--------|------------|
| Mudar a persona/tom da Sofia | `prompts/sofia.md` + `POST /prompts/refresh` |
| Adicionar/remover tool | `app/tools/bella_casa.py` + registrar em `app/agent.py:get_tools_registry` |
| Alterar horário de funcionamento ou cidades-matriz | `BUSINESS_HOURS` / `MATRIZ_CITIES` em `app/tools/bella_casa.py` |
| Mudar hora do lembrete de visita / lead frio | `app/scheduler.py` (`start_scheduler`) |
| Mudar mensagem de inatividade ou TTLs | constantes no topo de `app/routes/webhook.py` |
| Adicionar campo de lead | migration Alembic + atualizar Prisma do dashboard + `app/db/models.py` + `_lead_to_dict` + payload de `registrar_lead` |
| Trocar de UazAPI por outro provedor | `_send_whatsapp` + `_parse_uazapi_body` em `app/routes/webhook.py` |
| Ajustar UI do chat web | `chat/src/app/page.tsx` (proxy em `chat/src/app/api/[...path]/route.ts`) |
