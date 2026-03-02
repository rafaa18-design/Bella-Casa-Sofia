# Observabilidade (Monitoramento, Tracing e Metricas)

Este projeto utiliza uma stack de observabilidade composta por OpenTelemetry, Prometheus, Langfuse e logging estruturado -- sem dependencia de frameworks de agentes externos.

---

## Visao Geral da Arquitetura

| Componente | Arquivo | Funcao |
|------------|---------|--------|
| **OpenTelemetry Tracing** | `app/tracing.py` | Tracing distribuido (OTLP gRPC + Langfuse OTEL) |
| **Metricas Prometheus** | `app/metrics.py` | Contadores, histogramas e gauges expostos em `/metrics` |
| **Langfuse** | `app/langfuse_client.py` | Gestao de prompts versionados (nao tracing) |
| **Logging Estruturado** | `app/logging_config.py` | Logs JSON (producao) ou texto (desenvolvimento) |
| **Profiling Async** | `app/profiling.py` | Profiling de operacoes assincronas com percentis |
| **Debug Mode** | Endpoint `/run_debug` | Retorna trajetoria completa do agent loop |

---

## OpenTelemetry Tracing

O tracing distribuido eh configurado em `app/tracing.py`. A instrumentacao eh feita diretamente via OpenTelemetry SDK.

### Configuracao

O `setup_tracing()` eh chamado no startup da aplicacao e suporta dois exporters simultaneos:

1. **OTLP gRPC** -- para backends como Jaeger, Tempo, etc. (quando `OTEL_ENABLED=true`)
2. **Langfuse OTEL** -- para rastreamento de chamadas LLM no Langfuse (quando `LANGFUSE_ENABLED=true`)

```python
# app/tracing.py (simplificado)
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def setup_tracing(app=None):
    resource = Resource.create({
        "service.name": settings.MODULE_ID,
        "service.version": settings.MODULE_VERSION,
        "deployment.environment": settings.OTEL_ENVIRONMENT,
    })

    provider = TracerProvider(resource=resource)

    # Exporter OTLP gRPC (Jaeger, Tempo, etc.)
    if settings.OTEL_ENABLED and settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as GrpcSpanExporter,
        )
        grpc_exporter = GrpcSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            insecure=settings.OTEL_EXPORTER_OTLP_INSECURE,
        )
        provider.add_span_processor(BatchSpanProcessor(grpc_exporter))

    # Exporter Langfuse OTEL (via HTTP)
    if settings.LANGFUSE_ENABLED:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as HttpSpanExporter,
        )
        langfuse_auth = base64.b64encode(
            f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}".encode()
        ).decode()
        langfuse_exporter = HttpSpanExporter(
            endpoint=f"{settings.LANGFUSE_BASE_URL}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {langfuse_auth}"},
        )
        provider.add_span_processor(BatchSpanProcessor(langfuse_exporter))

    trace.set_tracer_provider(provider)

    # Instrumentar FastAPI (se OTEL habilitado)
    if app is not None and settings.OTEL_ENABLED:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/metrics")
```

### Variaveis de Ambiente

```bash
# OTLP generico (Jaeger, Tempo, etc.)
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_INSECURE=true
OTEL_ENVIRONMENT=development

# Langfuse OTEL (tracing de chamadas LLM)
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

### Shutdown

O `shutdown_tracing()` eh chamado no encerramento da aplicacao para garantir o flush dos spans pendentes:

```python
def shutdown_tracing():
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()
```

---

## Metricas Prometheus

Metricas sao coletadas em `app/metrics.py` e expostas no endpoint `GET /metrics` no formato Prometheus.

### Metricas Disponiveis

| Metrica | Tipo | Labels | Descricao |
|---------|------|--------|-----------|
| `http_requests_total` | Counter | `method`, `endpoint`, `status_code` | Total de requisicoes HTTP |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint` | Latencia das requisicoes |
| `http_requests_in_progress` | Gauge | `method`, `endpoint` | Requisicoes em andamento |
| `agent_runs_total` | Counter | `status`, `model` | Execucoes do agente |
| `agent_run_duration_seconds` | Histogram | `model` | Duracao das execucoes |
| `agent_tokens_total` | Counter | `type`, `model` | Tokens consumidos (input/output) |
| `memory_consolidation_total` | Counter | `status` | Consolidacoes de memoria (scheduled/completed/failed) |
| `memory_consolidation_duration_seconds` | Histogram | -- | Latencia da consolidacao |
| `rate_limit_hits_total` | Counter | `client_type` | Requisicoes bloqueadas por rate limit |
| `circuit_breaker_state` | Gauge | `name` | Estado do circuit breaker (0=closed, 1=open, 2=half-open) |
| `circuit_breaker_failures_total` | Counter | `name` | Falhas do circuit breaker |
| `errors_total` | Counter | `type`, `source` | Total de erros |
| `redis_operations_total` | Counter | `operation`, `status` | Operacoes Redis |
| `auth_attempts_total` | Counter | `status` | Tentativas de autenticacao |

### Middleware de Metricas

O `MetricsMiddleware` eh adicionado automaticamente ao FastAPI e coleta metricas de todas as requisicoes HTTP (exceto `/metrics` para evitar recursao). Paths dinamicos sao normalizados para reduzir cardinalidade:

```python
from app.metrics import MetricsMiddleware
app.add_middleware(MetricsMiddleware)
```

### Registrando Metricas no Codigo

```python
from app.metrics import record_agent_run, record_error, record_consolidation

# Apos uma execucao do agente
record_agent_run(
    status="success",
    model="anthropic/claude-sonnet-4-20250514",
    latency_seconds=2.5,
    input_tokens=1500,
    output_tokens=800,
)

# Registrar um erro
record_error(error_type="timeout", source="model")

# Registrar consolidacao de memoria
record_consolidation(status="completed", duration_seconds=1.2)
```

### Configuracao

```bash
METRICS_ENABLED=true
```

---

## Langfuse (Gestao de Prompts)

O Langfuse eh utilizado **exclusivamente para gestao de prompts versionados**, nao para tracing. O tracing de chamadas LLM eh feito via OpenTelemetry (descrito acima).

### Cliente

O cliente Langfuse eh inicializado em `app/langfuse_client.py`:

```python
# app/langfuse_client.py
from langfuse import Langfuse
from app.config import settings

_langfuse: Langfuse | None = None

def get_langfuse() -> Langfuse | None:
    """Retorna o cliente Langfuse. None se nao configurado."""
    global _langfuse

    if not settings.LANGFUSE_ENABLED:
        return None

    if _langfuse is None:
        _langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_BASE_URL,
        )
        if not _langfuse.auth_check():
            _langfuse = None

    return _langfuse
```

### Endpoints de Prompts

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/prompts/webhook` | POST | Webhook para atualizacao de prompts |
| `/prompts/refresh` | POST | Forcar atualizacao do prompt em cache |
| `/prompts/current` | GET | Visualizar prompt atual em cache |

### Variaveis de Ambiente

```bash
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

---

## Debug Mode (Endpoint `/run_debug`)

O modo de debug eh acessado via o endpoint `POST /run_debug` do padrao AgentBench. O `/run_debug` retorna a **trajetoria completa** da execucao do agent loop, incluindo:

- Todas as mensagens trocadas entre o LLM e o sistema
- Chamadas de ferramentas com argumentos e resultados
- Tokens consumidos
- Duracao total e por etapa

### Exemplo de Uso

```bash
curl -X POST http://localhost:8000/run_debug \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"type": "text", "content": "Qual o horario disponivel amanha?"}],
    "conversation_id": "debug-001"
  }'
```

A resposta inclui o campo `trajectory` com a sequencia completa de passos executados pelo agente.

---

## Logging Estruturado

O sistema de logging eh configurado em `app/logging_config.py` e suporta dois formatos:

### JSON (Producao)

```json
{
  "timestamp": "2025-01-15T10:30:00.000000+00:00",
  "level": "INFO",
  "logger": "app.agent_loop",
  "message": "Agent run completed",
  "module": "agent_loop",
  "function": "run_agent_loop",
  "line": 42,
  "request_id": "abc12345"
}
```

### Texto (Desenvolvimento)

```
2025-01-15 10:30:00 | INFO     | [abc12345] app.agent_loop | Agent run completed
```

### Configuracao

```python
# Chamado no startup da aplicacao
from app.logging_config import setup_logging
setup_logging()
```

```bash
# Variaveis de ambiente
LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json         # json ou text
```

### Context Logger com Request ID

O `request_id` eh propagado automaticamente via `ContextVar` para correlacionar logs de uma mesma requisicao:

```python
from app.logging_config import get_context_logger

logger = get_context_logger(__name__)
logger.info("Operacao concluida", extra={"tokens": 1500})
```

---

## Profiling Async

O modulo `app/profiling.py` fornece utilitarios para medir performance de operacoes assincronas.

### Context Manager

```python
from app.profiling import profile_async

async def minha_operacao():
    async with profile_async("busca_redis", log_slow_threshold_ms=100):
        resultado = await redis.get("chave")
```

Se a operacao exceder o `log_slow_threshold_ms`, um warning eh emitido automaticamente.

### Decorator

```python
from app.profiling import profile_async_function

@profile_async_function(log_slow_threshold_ms=500)
async def processar_dados(dados: dict):
    # operacao demorada
    ...
```

### Estatisticas Agregadas

O profiler coleta amostras e expoe estatisticas (media, min, max, p50, p95, p99) via o endpoint `GET /profiling`:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/profiling
```

Resposta:

```json
{
  "busca_redis": {
    "name": "busca_redis",
    "count": 150,
    "success_rate": 0.98,
    "mean_ms": 12.5,
    "min_ms": 1.2,
    "max_ms": 85.3,
    "p50_ms": 8.0,
    "p95_ms": 45.2,
    "p99_ms": 72.1
  }
}
```

### Profiling de Operacoes Concorrentes

```python
from app.profiling import profile_concurrent

results = await profile_concurrent({
    "fetch_user": fetch_user(user_id),
    "fetch_history": fetch_history(conversation_id),
}, log_slow_threshold_ms=200)

for name, (result, profile) in results.items():
    print(f"{name}: {profile.duration_ms:.2f}ms")
```

---

## Resumo: Fluxo de Observabilidade

```
Requisicao HTTP
  |
  +-- MetricsMiddleware -----> Prometheus (http_requests_total, latencia, etc.)
  |
  +-- ProfilingMiddleware ---> AsyncProfiler (estatisticas em /profiling)
  |
  +-- LoggingConfig ---------> stdout (JSON ou texto com request_id)
  |
  +-- FastAPIInstrumentor ---> OTLP gRPC (Jaeger/Tempo)
  |                            Langfuse OTEL (tracing LLM)
  |
  +-- Agent Loop
       |
       +-- record_agent_run() ---------> Prometheus (agent_runs_total, tokens, duracao)
       +-- record_consolidation() -----> Prometheus (memory_consolidation_total)
       +-- record_rate_limit_hit() ----> Prometheus (rate_limit_hits_total)
       +-- record_circuit_breaker() ---> Prometheus (circuit_breaker_state)
```

---

## Variaveis de Ambiente (Completo)

```bash
# OpenTelemetry
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_INSECURE=true
OTEL_ENVIRONMENT=development

# Langfuse (prompts + OTEL tracing)
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com

# Metricas Prometheus
METRICS_ENABLED=true

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## Referencias

- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Prometheus Client Python](https://github.com/prometheus/client_python)
- [Langfuse Documentation](https://langfuse.com/docs)
- [FastAPI OpenTelemetry](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html)
