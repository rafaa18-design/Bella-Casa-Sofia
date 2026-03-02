# Deploy e Producao

Este documento cobre deploy, configuracao de ambiente, seguranca e monitoramento para o template de agente com LiteLLM + FastAPI.

---

## Arquitetura de Producao

O agente roda como uma aplicacao **FastAPI pura**. As dependencias principais sao:

- **LiteLLM** (`litellm>=1.55.0`): Abstrai chamadas a multiplos providers (Anthropic, OpenAI, Vertex AI)
- **json-repair** (`json-repair>=0.30.0`): Reparo de JSON malformado em respostas do LLM
- **Redis**: Session state, historico de mensagens, cache e memoria consolidada
- **PostgreSQL**: Opcional (para dados de dominio; nao e usado pelo agent loop)

---

## Variaveis de Ambiente

### Producao Minima

```bash
# Identificacao
MODULE_ID=meu-agente
MODULE_VERSION=1.0.0

# LLM (pelo menos uma chave)
ANTHROPIC_API_KEY=sk-ant-...
# ou
OPENAI_API_KEY=sk-...

# Autenticacao
AUTH_ENABLED=true
JWT_SECRET=chave-secreta-longa-e-segura-minimo-32-chars
AUTH_USERS='{"admin": "$2b$12$..."}'  # Hashes bcrypt

# Storage
REDIS_URL=redis://redis:6379/0
```

### Opcional: Observabilidade

```bash
# Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
LANGFUSE_ENABLED=true

# Prometheus
METRICS_ENABLED=true

# OpenTelemetry
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

### Todas as Variaveis

| Variavel | Descricao | Padrao |
|----------|-----------|--------|
| `MODULE_ID` | ID unico do modulo | `clinica-odontologica` |
| `MODULE_VERSION` | Versao semantica | `1.0.0` |
| `DEFAULT_MODEL` | Modelo LiteLLM padrao | `gpt-5-mini` |
| `MODEL_PROVIDER` | Provider (`anthropic`, `openai`, `vertexai`) | `anthropic` |
| `AUTH_ENABLED` | Habilitar autenticacao JWT | `true` |
| `JWT_SECRET` | Chave para tokens JWT | - (obrigatorio) |
| `JWT_ALGORITHM` | Algoritmo JWT | `HS256` |
| `JWT_EXPIRATION_HOURS` | Expiracao do token | `24` |
| `AUTH_USERS` | Credenciais JSON (bcrypt) | - |
| `REDIS_URL` | URL de conexao Redis | `redis://localhost:6379/0` |
| `REDIS_SESSION_TTL` | TTL de sessao (segundos) | `86400` (24h) |
| `REDIS_POOL_MAX_SIZE` | Conexoes maximas Redis | `20` |
| `MEMORY_CONSOLIDATION_ENABLED` | Consolidacao de memoria LLM | `true` |
| `MEMORY_WINDOW` | Mensagens antes de consolidar | `20` |
| `MEMORY_CONSOLIDATION_MODEL` | Modelo para consolidacao | (usa `DEFAULT_MODEL`) |
| `TOOL_OUTPUT_MAX_CHARS` | Limite de caracteres no output de tools | `500` |
| `NUM_HISTORY_RUNS` | Historico (sem consolidacao) | `2` |
| `MAX_TURNS` | Turnos maximos no agent loop | `10` |
| `TOOL_CALL_LIMIT` | Chamadas de tool por turno | `5` |
| `MAX_OUTPUT_TOKENS` | Tokens maximos na resposta | `2048` |
| `CACHE_SYSTEM_PROMPT` | Cache de system prompt | `true` |
| `LOG_LEVEL` | Nivel de log | `INFO` |
| `LOG_FORMAT` | Formato de log (`json`/`text`) | `json` |
| `CORS_ORIGINS` | Origens CORS permitidas | `["http://localhost:3000", ...]` |
| `RATE_LIMIT_ENABLED` | Habilitar rate limiting | `true` |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | Limite de requisicoes/minuto | `60` |
| `SHUTDOWN_TIMEOUT` | Timeout de graceful shutdown (s) | `30` |

---

## Docker Compose

### Producao

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  agent:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - MODULE_ID=${MODULE_ID}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - REDIS_URL=redis://redis:6379/0
      - AUTH_ENABLED=true
      - JWT_SECRET=${JWT_SECRET}
      - AUTH_USERS=${AUTH_USERS}
      - MEMORY_CONSOLIDATION_ENABLED=true
      - MEMORY_WINDOW=20
      - LANGFUSE_ENABLED=${LANGFUSE_ENABLED:-false}
      - LANGFUSE_PUBLIC_KEY=${LANGFUSE_PUBLIC_KEY:-}
      - LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY:-}
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  redis_data:
```

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copiar arquivos de dependencias
COPY pyproject.toml uv.lock ./

# Instalar dependencias
RUN uv sync --frozen --no-dev

# Copiar codigo
COPY app/ app/

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Executar
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Seguranca

### Autenticacao JWT

O middleware JWT e customizado (`app/auth.py`), sem dependencia de frameworks externos. Rotas publicas (sem autenticacao):

- `GET /health`
- `POST /auth/login`
- `GET /metrics`

Todas as demais rotas exigem token JWT no header `Authorization: Bearer <token>`.

```bash
# Gerar hash bcrypt para senha
uv run scripts/hash_password.py --password minha_senha --json --username admin

# Configurar usuarios (bcrypt obrigatorio em producao)
AUTH_USERS='{"admin": "$2b$12$..."}'

# Obter token
curl -X POST "http://localhost:8000/auth/login?username=admin&password=minha_senha"

# Usar token
curl -H "Authorization: Bearer <token>" http://localhost:8000/metadata
```

### Boas Praticas

| Aspecto | Recomendacao |
|---------|--------------|
| `JWT_SECRET` | Minimo 32 caracteres, unico por ambiente |
| API Keys | Nunca commitar, usar secrets manager |
| `REDIS_URL` | Senha forte, TLS em producao |
| Endpoints | Sempre autenticar exceto health/login/metrics |
| Tools | Validar inputs, nao executar codigo arbitrario |
| Logs | Nao logar dados sensiveis (configurar `LOG_FORMAT=json`) |
| CORS | Configurar `CORS_ORIGINS` com origens especificas |
| Senhas | Sempre bcrypt (nunca plain text em producao) |

### Validacao em Tools

```python
from app.runtime import tool, RunContext, RetryAgentRun, StopAgentRun
import re


@tool
def processar_email(run_context: RunContext, email: str) -> str:
    """Processa e valida um endereco de email."""
    # Validar formato
    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        raise RetryAgentRun(
            "Email invalido. Use formato: usuario@dominio.com"
        )

    # Validar dominio
    blocked_domains = ['spam.com', 'fake.com']
    domain = email.split('@')[1]
    if domain in blocked_domains:
        raise StopAgentRun("Dominio bloqueado.")

    return f"Email {email} processado"
```

### Rate Limiting

O rate limiting e integrado ao template via `app/rate_limiter.py`, com suporte a Redis e fallback em memoria:

```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

---

## Checklist de Deploy

### Pre-Deploy

- [ ] Todas as variaveis de ambiente configuradas
- [ ] `JWT_SECRET` e unico e seguro (minimo 32 chars)
- [ ] API keys configuradas no secrets manager
- [ ] Redis acessivel e saudavel
- [ ] `AUTH_USERS` com hashes bcrypt (nao plain text)
- [ ] `CORS_ORIGINS` configurado para origens de producao
- [ ] Testes passando (`uv run pytest`)

### Deploy

- [ ] Docker build sem erros
- [ ] Healthcheck funcionando (`/health` retorna 200)
- [ ] Logs sem erros criticos (`LOG_FORMAT=json`)
- [ ] Metricas sendo coletadas (se `METRICS_ENABLED=true`)

### Pos-Deploy

- [ ] `GET /health` retorna 200 (inclui status do Redis)
- [ ] `GET /metadata` retorna dados corretos
- [ ] `POST /auth/login` autentica corretamente
- [ ] `POST /run` processa requisicoes com ferramentas
- [ ] Consolidacao de memoria funcionando (se habilitada)
- [ ] Observabilidade configurada (Langfuse / Prometheus / OTEL)

---

## Monitoramento

### Endpoints de Health

```bash
# Health basico (inclui status Redis)
curl http://localhost:8000/health

# Metadata do modulo
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/metadata

# Metricas Prometheus
curl http://localhost:8000/metrics
```

### Metricas Disponiveis (Prometheus)

| Metrica | Descricao |
|---------|-----------|
| `http_requests_total` | Requisicoes por metodo/path/status |
| `http_request_duration_seconds` | Latencia das requisicoes |
| `http_requests_in_progress` | Requisicoes em andamento |
| `agent_runs_total` | Execucoes do agente por status |
| `agent_run_duration_seconds` | Duracao das execucoes |
| `memory_consolidation_total` | Consolidacoes por status |
| `memory_consolidation_duration_seconds` | Latencia da consolidacao |
| `rate_limit_hits_total` | Requisicoes bloqueadas |
| `circuit_breaker_state` | Estado do circuit breaker |

### Logs Estruturados

```python
import logging

logger = logging.getLogger(__name__)

logger.info(
    "request_processed",
    extra={
        "conversation_id": conversation_id,
        "latency_ms": latency_ms,
        "tokens_used": tokens_used,
    },
)
```

Formato configuravel via `LOG_FORMAT`:
- `json`: Producao (parseavel por ferramentas de log)
- `text`: Desenvolvimento (legivel no terminal)

---

## Comandos de Deploy

```bash
# Build e deploy com Docker Compose
docker compose -f docker-compose.prod.yml up -d --build

# Ver logs
docker compose -f docker-compose.prod.yml logs -f agent

# Restart
docker compose -f docker-compose.prod.yml restart agent

# Verificar saude
curl http://localhost:8000/health
```

---

## Graceful Shutdown

O sistema implementa shutdown gracioso com as seguintes etapas:

1. Para de aceitar novas requisicoes
2. Aguarda requisicoes em andamento (ate `SHUTDOWN_TIMEOUT` segundos)
3. Aguarda consolidacoes de memoria ativas
4. Fecha conexoes Redis (`close_redis()`)
5. Flush de traces e metricas

```bash
SHUTDOWN_TIMEOUT=30  # Segundos para aguardar requisicoes em andamento
```

---

## Referencia de Dependencias

| Pacote | Proposito |
|--------|-----------|
| `litellm>=1.55.0` | Abstração multi-provider LLM |
| `json-repair>=0.30.0` | Reparo de JSON malformado |
| `fastapi` | Framework web |
| `uvicorn` | Servidor ASGI |
| `redis[hiredis]` | Cliente Redis async |
| `pydantic-settings` | Configuracao via env vars |
| `bcrypt` / `pyjwt` | Autenticacao |
| `prometheus-client` | Metricas |
| `opentelemetry-*` | Tracing distribuido |

---

## Referencias

- [Docker Documentation](https://docs.docker.com)
- [Uvicorn Deployment](https://www.uvicorn.org/deployment/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [LiteLLM Documentation](https://docs.litellm.ai/)
- [Redis Documentation](https://redis.io/docs/)
