# Arquitetura da Aplicacao FastAPI

Este projeto utiliza uma aplicacao FastAPI pura como runtime. Toda a infraestrutura -- autenticacao, rate limiting, seguranca, ciclo de vida -- e implementada de forma customizada.

---

## Visao Geral

A aplicacao e criada diretamente via `FastAPI(...)` em `app/main.py`, com um `lifespan` context manager que gerencia startup e shutdown. Nao existe nenhum wrapper ou runtime intermediario.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: conectar Redis, carregar prompts, setup tracing
    setup_tracing(app)
    get_langfuse()
    await get_redis()
    prompt = await get_prompt_manager().get_prompt()

    yield

    # Shutdown: aguardar requests, fechar conexoes
    await shutdown_consolidation(timeout=5.0)
    shutdown_tracing()
    await close_redis()
    langfuse_shutdown()

custom_app = FastAPI(
    title=settings.MODULE_DESCRIPTION,
    version=settings.MODULE_VERSION,
    lifespan=lifespan,
)

app = custom_app
```

### Principios da Arquitetura

| Principio | Descricao |
|-----------|-----------|
| **Sem framework externo** | FastAPI puro com LiteLLM para chamadas LLM |
| **Contrato AgentBench** | Endpoints padrao `/metadata`, `/run`, `/run_debug` |
| **Soberania do modulo** | O modulo gerencia seu proprio pipeline, estado e contexto |
| **Middlewares customizados** | JWT, rate limiting, seguranca e metricas implementados internamente |

---

## Middlewares

Os middlewares sao aplicados em `app/main.py` na ordem inversa de execucao (o ultimo adicionado executa primeiro). A pilha completa:

```python
# 1. CORS (executa primeiro)
app.add_middleware(CORSMiddleware, ...)

# 2. Security Headers
app.add_middleware(SecurityHeadersMiddleware)

# 3. JWT Authentication
app.add_middleware(JWTAuthMiddleware)

# 4. Rate Limiting (Redis-backed)
app.add_middleware(RedisRateLimitMiddleware, requests_per_minute=60)

# 5. Metricas Prometheus
app.add_middleware(MetricsMiddleware)

# 6. Request ID (executa por ultimo, mais proximo da request)
app.add_middleware(RequestIDMiddleware)
```

### RequestIDMiddleware

Adiciona um ID unico a cada request para rastreabilidade. Aceita `X-Request-ID` do header ou gera um UUID.

```python
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers['X-Request-ID'] = request_id
            return response
        finally:
            request_id_var.reset(token)
```

**Arquivo**: `app/main.py`

### JWTAuthMiddleware

Autenticacao JWT customizada usando a biblioteca `pyjwt`. Valida tokens Bearer em todas as requests, exceto rotas publicas.

```python
class JWTAuthMiddleware(BaseHTTPMiddleware):
    EXCLUDED_PATHS = [
        '/', '/health', '/metrics', '/docs', '/redoc',
        '/openapi.json', '/auth/login', '/auth/token',
        '/prompt/webhook',
    ]

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        if request.method == 'OPTIONS':
            return await call_next(request)

        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return JSONResponse(status_code=401, content={...})

        token = auth_header.split(' ', 1)[1]
        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
            )
            request.state.user = payload
        except jwt.ExpiredSignatureError:
            return JSONResponse(status_code=401, ...)
        except jwt.InvalidTokenError:
            return JSONResponse(status_code=401, ...)

        return await call_next(request)
```

**Arquivo**: `app/main.py`

**Configuracao**:

```bash
AUTH_ENABLED=true
JWT_SECRET=chave-secreta-forte-minimo-32-chars
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
```

### SecurityHeadersMiddleware

Adiciona headers de seguranca a todas as respostas: HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy.

```python
from app.security import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware)
```

Os headers adicionados incluem:

| Header | Valor Padrao |
|--------|-------------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; ...` |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), ...` |

**Arquivo**: `app/security.py`

### RedisRateLimitMiddleware

Rate limiting com janela deslizante (sliding window), usando Redis como backend distribuido. Quando Redis nao esta disponivel, faz fallback para rate limiting em memoria.

```python
from app.rate_limiter import RateLimitMiddleware as RedisRateLimitMiddleware

app.add_middleware(
    RedisRateLimitMiddleware,
    requests_per_minute=settings.RATE_LIMIT_REQUESTS_PER_MINUTE,
)
```

Caracteristicas:

- **Identificacao por usuario**: Extrai `sub` do token JWT para rate limit por usuario
- **Fallback por IP**: Quando nao ha token, usa IP do cliente
- **Headers informativos**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- **Rotas excluidas**: `/`, `/health`, `/docs`, `/openapi.json`, `/metrics`
- **Audit logging**: Registra bloqueios por rate limit

**Arquivo**: `app/rate_limiter.py`

**Configuracao**:

```bash
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

### MetricsMiddleware

Coleta metricas HTTP para Prometheus: contagem de requests, latencia, requests em andamento.

```python
from app.metrics import MetricsMiddleware

app.add_middleware(MetricsMiddleware)
```

**Arquivo**: `app/metrics.py`

**Configuracao**:

```bash
METRICS_ENABLED=true
```

---

## Ciclo de Vida (Lifespan)

O `lifespan` context manager em `app/main.py` gerencia todo o ciclo de vida da aplicacao:

### Startup

1. Configuracao do OpenTelemetry tracing
2. Inicializacao do Langfuse (observabilidade)
3. Conexao com Redis (session state, cache, rate limiting)
4. Pre-carregamento do prompt no cache

### Shutdown (Graceful)

1. Aguarda requests em andamento (ate `SHUTDOWN_TIMEOUT` segundos)
2. Aguarda consolidacoes de memoria ativas
3. Encerra tracing (flush de spans)
4. Fecha conexoes Redis
5. Shutdown do Langfuse

```bash
SHUTDOWN_TIMEOUT=30  # segundos
```

---

## Endpoints

### AgentBench (Contrato Padrao)

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/metadata` | GET | Capacidades e configuracao do modulo |
| `/run` | POST | Execucao do agente em producao |
| `/run_debug` | POST | Execucao com trajetoria completa para observabilidade |

### Sistema

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/` | GET | Informacoes basicas do modulo |
| `/health` | GET | Health check (verifica Redis) |
| `/metrics` | GET | Metricas Prometheus |
| `/profiling` | GET | Estatisticas de profiling async |

### Autenticacao

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/auth/login` | POST | Login com usuario/senha, retorna JWT |
| `/auth/token` | POST | Criacao programatica de tokens (requer scope admin) |

### Gestao de Prompts

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/prompt/webhook` | POST | Webhook do Langfuse para atualizar prompts |
| `/prompt/refresh` | POST | Forcar refresh do prompt |
| `/prompt/current` | GET | Ver prompt atual em cache |

---

## Routers

A aplicacao organiza endpoints em routers FastAPI:

```python
# AgentBench endpoints
agentbench_router = APIRouter(tags=['AgentBench'])
custom_app.include_router(agentbench_router)

# Autenticacao
auth_router = APIRouter(prefix='/auth', tags=['Authentication'])
custom_app.include_router(auth_router)

# Gestao de prompts
prompt_router = APIRouter(prefix='/prompt', tags=['Prompt'])
custom_app.include_router(prompt_router)

# Sistema (health, metrics, root)
system_router = APIRouter(tags=['System'])
custom_app.include_router(system_router)
```

---

## Autenticacao JWT

### Fluxo de Login

```
POST /auth/login?username=admin&password=senha
  -> Valida credenciais (bcrypt) contra AUTH_USERS
  -> Gera token JWT com scopes ['agents:read', 'agents:run']
  -> Retorna { access_token, token_type, expires_in }
```

### Criacao de Tokens (Admin)

```
POST /auth/token?user_id=novo_usuario&scopes=read,write
  Authorization: Bearer <admin-token>
  -> Verifica se o caller tem scope admin
  -> Gera token para o usuario especificado
  -> Registra audit log
```

### Configuracao de Usuarios

```bash
# Gerar hash bcrypt
uv run scripts/hash_password.py --password minha_senha

# Configurar usuarios no .env
AUTH_USERS='{"admin": "$2b$12$hash_bcrypt_aqui"}'
AUTH_ADMIN_SCOPES='["admin"]'
```

---

## Funcionalidades que Requerem Implementacao Customizada

Esta arquitetura e minimalista e extensivel. Algumas funcionalidades nao estao incluidas e precisariam de implementacao customizada:

| Funcionalidade | Status | Como Implementar |
|----------------|--------|-----------------|
| **HITL (Human-in-the-Loop)** | Nao incluido | Criar tool que pausa execucao e aguarda input via webhook/polling |
| **RBAC granular** | Parcial | JWT com scopes existe; adicionar verificacao de scopes por endpoint |
| **Background Tasks** | Parcial | Usar `asyncio.create_task()` ou Celery para tarefas longas |
| **Remote Execution** | Nao incluido | Criar cliente HTTP para chamar outros modulos via API |
| **MCP Server** | Nao incluido | Implementar protocolo MCP como endpoints adicionais |
| **A2A Protocol** | Nao incluido | Implementar protocolo Agent-to-Agent como endpoints |

### Exemplo: Background Task Simples

```python
import asyncio
from fastapi import BackgroundTasks

@app.post("/processar")
async def processar(background_tasks: BackgroundTasks):
    background_tasks.add_task(tarefa_longa, dados)
    return {"status": "processando"}

async def tarefa_longa(dados):
    # Processamento assincrono
    await asyncio.sleep(10)
    # Salvar resultado no Redis
```

### Exemplo: Verificacao de Scope por Endpoint

```python
from fastapi import Request, HTTPException

def require_scope(request: Request, required: str):
    """Verificar se o usuario tem o scope necessario."""
    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=401)
    scopes = user.get('scopes', [])
    if required not in scopes and 'admin' not in scopes:
        raise HTTPException(status_code=403, detail=f"Scope '{required}' necessario")

@app.post("/admin/operacao")
async def operacao_admin(request: Request):
    require_scope(request, 'admin')
    return {"resultado": "ok"}
```

---

## Observabilidade

### Metricas Prometheus (`/metrics`)

```
http_requests_total{method, path, status}
http_request_duration_seconds{method, path}
http_requests_in_progress
agent_runs_total{status}
agent_run_duration_seconds
memory_consolidation_total{status}
rate_limit_hits_total{client_type}
circuit_breaker_state
```

### OpenTelemetry Tracing

```python
from app.tracing import create_span

async def minha_funcao():
    with create_span('operacao', {'user_id': uid}) as span:
        resultado = await processar()
        span.set_attribute('result_size', len(resultado))
```

### Audit Logging

Operacoes sensiveis sao registradas via `app/audit.py`:

- Login (sucesso/falha)
- Execucao do agente (inicio/sucesso/falha)
- Criacao de tokens
- Bloqueios por rate limit
- Acessos negados

---

## Arquivos Relevantes

| Arquivo | Responsabilidade |
|---------|-----------------|
| `app/main.py` | Aplicacao FastAPI, middlewares, endpoints, lifespan |
| `app/security.py` | SecurityHeadersMiddleware |
| `app/rate_limiter.py` | RedisRateLimitMiddleware e RedisRateLimiter |
| `app/metrics.py` | MetricsMiddleware e metricas Prometheus |
| `app/auth.py` | Funcoes de autenticacao (bcrypt, scopes) |
| `app/audit.py` | Audit logging para operacoes sensiveis |
| `app/config.py` | Settings (pydantic-settings) |
| `app/storage.py` | Redis (connection pool, session state, cache) |
| `app/tracing.py` | OpenTelemetry distributed tracing |
