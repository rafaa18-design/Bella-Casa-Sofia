# Migração Railway → Render — Sofia (Bella Casa)

Guia passo a passo para subir a agente Sofia no Render usando o runtime Python nativo.

---

## Antes de começar — o que você precisa em mãos

Copie estes valores do Railway antigo (aba **Variables** do serviço Sofia) antes de desligar:

- `DATABASE_URL` (Neon — você já tem)
- `REDIS_URL` (o do Railway vai morrer junto — veremos um novo no Passo 1)
- `OPENAI_API_KEY`
- `UAZAPI_URL` e `UAZAPI_TOKEN`
- `FIREBASE_ADMIN_TOKEN`
- `JWT_SECRET`

---

## Passo 1 — Criar um Redis novo (Upstash, grátis)

O Redis do Railway some quando a cota acaba. O Upstash tem free tier e funciona com o Render.

1. Acesse **upstash.com** → crie conta → **Create Database** (tipo Redis)
2. Região: escolha **us-east** (perto do Render Oregon/Virginia)
3. Na tela do banco, copie a **connection string** no formato `rediss://...` (com TLS)
4. Guarde — será o `REDIS_URL` no Passo 4

> Observação: a Sofia tem fallback em memória se o Redis faltar, mas aí ela perde o estado de handoff a cada restart. Para produção, use o Upstash.

---

## Passo 2 — Commitar o blueprint

Eu criei o arquivo `render.yaml` na raiz do repositório. Confirme que ele está commitado e no GitHub na branch que você quer deployar (ex: `rafael`):

```bash
cd "asani-ai-agent-template"
git add render.yaml RENDER_DEPLOY.md
git commit -m "chore: blueprint de deploy no Render"
git push asani rafael
```

---

## Passo 3 — Criar o serviço no Render

**Opção A — via Blueprint (recomendado, usa o render.yaml):**

1. Acesse **dashboard.render.com** → **New** → **Blueprint**
2. Conecte o repositório `operacoesasani/bella-casa-ia-leads`
3. O Render lê o `render.yaml` e mostra o serviço `bella-casa-sofia`
4. Ele vai pedir os valores das variáveis marcadas como `sync: false` — preencha no Passo 4
5. Clique em **Apply**

**Opção B — manual (sem blueprint):**

1. **New** → **Web Service** → conecte o repo → branch `rafael`
2. **Language:** Python 3
3. **Build Command:** `pip install uv && uv sync --frozen`
4. **Start Command:** `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. **Health Check Path:** `/health`
6. **Instance Type:** Free

---

## Passo 4 — Configurar as variáveis de ambiente

No serviço criado → aba **Environment** → adicione:

| Variável | Valor |
|---|---|
| `PYTHON_VERSION` | `3.13.4` |
| `DATABASE_URL` | URL do Neon |
| `POSTGRES_URL` | a MESMA URL do Neon |
| `REDIS_URL` | string do Upstash (`rediss://...`) |
| `OPENAI_API_KEY` | sua chave |
| `UAZAPI_URL` | `https://free.uazapi.com` |
| `UAZAPI_TOKEN` | seu token |
| `FIREBASE_ADMIN_TOKEN` | o mesmo do Railway |
| `JWT_SECRET` | o mesmo do Railway (32+ chars) |
| `AGENT_NAME` | `sofia` (se não veio do blueprint) |
| `AGENT_PROMPT_NAME` | `sofia` |
| `DEFAULT_MODEL` | `gpt-5-mini` |
| `MODEL_PROVIDER` | `openai` |

Clique em **Save Changes** — o Render faz o deploy.

---

## Passo 5 — Verificar o deploy

1. Aguarde o build terminar (aba **Logs**: procure por `Uvicorn running`)
2. Copie a URL pública do serviço (ex: `https://bella-casa-sofia.onrender.com`)
3. Teste o health:
   ```bash
   curl https://bella-casa-sofia.onrender.com/health
   ```
   Deve responder OK. Se der erro, veja a aba **Logs**.

---

## Passo 6 — Apontar o WhatsApp (UazAPI) para o Render

No painel da UazAPI, troque a URL do webhook de:
```
https://<antigo>.railway.app/webhook
```
para:
```
https://bella-casa-sofia.onrender.com/webhook
```

---

## Passo 7 — Atualizar o dashboard

No deploy do dashboard (Vercel/Render), atualize a variável:
```
AGENT_URL=https://bella-casa-sofia.onrender.com
```
Assim o salvamento de personalização da Sofia continua funcionando.

---

## Passo 8 — Aplicar migrations (se necessário)

Se o banco Neon ainda não tem o schema, rode uma vez (local ou via Render Shell):
```bash
uv run alembic upgrade head
```
(Se você já usa o mesmo Neon do dashboard, o schema já existe — pule.)

---

## ⚠️ Atenção: limites do plano Free do Render

- **Sleep por inatividade:** o serviço Free dorme após ~15 min sem tráfego. A primeira mensagem do WhatsApp depois disso pode demorar ~50s (cold start) ou se perder.
- **Solução barata:** um ping a cada 10 min em `/health` (ex: cron-job.org) mantém acordado, OU suba para o plano **Starter** (US$ 7/mês) que não dorme.
- **Horas mensais:** o Free tem limite de horas — monitore na aba **Metrics**.

---

## Resumo do que muda em relação ao Railway

| Item | Railway | Render |
|---|---|---|
| Build | nixpacks (`railway.toml`) | `uv sync` (render.yaml / native) |
| Porta | `$PORT` | `$PORT` (start command já usa) |
| Redis | bundled | Upstash externo |
| Postgres | bundled / Neon | Neon (mantém) |
| Webhook UazAPI | `*.railway.app/webhook` | `*.onrender.com/webhook` |

O `railway.toml` pode ficar no repo sem problema — o Render ignora ele e usa o `render.yaml`.
