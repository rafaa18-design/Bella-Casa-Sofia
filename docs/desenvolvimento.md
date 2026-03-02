# Desenvolvimento e Testes

Este documento cobre a estrutura de testes, debugging, troubleshooting, profiling e padroes de desenvolvimento do template.

---

## Estrutura de Testes

```
tests/
├── __init__.py
├── conftest.py        # Fixtures compartilhadas
├── test_api.py        # Testes de endpoints
├── test_tools.py      # Testes de tools
└── test_agent.py      # Testes do agente
```

---

## Fixtures Uteis

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Cliente de teste sem autenticacao."""
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """Cliente de teste com JWT valido."""
    response = client.post(
        "/auth/login",
        params={"username": "test", "password": "password"},
    )
    if response.status_code == 200:
        token = response.json().get("access_token")
        client.headers["Authorization"] = f"Bearer {token}"
    return client
```

---

## Testando Tools

As tools utilizam `RunContext`, `RetryAgentRun` e `StopAgentRun` do modulo `app.runtime` (runtime proprio do projeto, sem dependencia de frameworks externos):

```python
# tests/test_tools.py
import pytest
from app.runtime import RunContext, RetryAgentRun, StopAgentRun
from app.tools import calculate, format_date


class TestCalculateTool:
    def test_simple_addition(self):
        """Testa chamada direta da funcao da tool."""
        result = calculate.func("2 + 2")
        assert result == "4"

    def test_division_by_zero_raises_retry(self):
        """RetryAgentRun envia feedback ao LLM para corrigir."""
        with pytest.raises(RetryAgentRun) as exc:
            calculate.func("10 / 0")
        assert "Division by zero" in str(exc.value)


class TestFormatDateTool:
    def test_iso_format(self):
        result = format_date.func("2024-01-15")
        assert result == "2024-01-15"

    def test_invalid_date_raises_retry(self):
        with pytest.raises(RetryAgentRun):
            format_date.func("invalid")
```

### Testando Tools que Usam RunContext

```python
from app.runtime import RunContext

class TestToolComContexto:
    def test_salvar_dados(self):
        """Tools que recebem run_context precisam de um RunContext."""
        ctx = RunContext(
            session_state={},
            session_id="test-session",
            user_id="test-user",
        )
        result = salvar_dados_cliente.func(
            run_context=ctx,
            nome="Joao",
            convenio="OdontoPrev",
        )
        assert "Joao" in ctx.session_state.get("cliente_nome", "")
```

---

## Testando Endpoints AgentBench

```python
# tests/test_api.py
class TestAgentBenchEndpoints:
    def test_metadata(self, auth_client):
        response = auth_client.get("/metadata")
        assert response.status_code == 200
        data = response.json()
        assert "module_id" in data
        assert "capabilities" in data

    def test_run_validation(self, auth_client):
        response = auth_client.post("/run", json={})
        assert response.status_code == 422

    def test_run_with_valid_input(self, auth_client):
        response = auth_client.post("/run", json={
            "input": [{"type": "text", "content": "Ola"}],
            "conversation_id": "test_001",
        })
        assert response.status_code == 200
        data = response.json()
        assert "final_output" in data
        assert "metrics" in data

    def test_run_debug_returns_trajectory(self, auth_client):
        """O endpoint /run_debug retorna a trajetoria completa."""
        response = auth_client.post("/run_debug", json={
            "input": [{"type": "text", "content": "Ola"}],
            "conversation_id": "test_debug_001",
        })
        assert response.status_code == 200
        data = response.json()
        assert "trajectory" in data
```

---

## Rodando Testes

```bash
# Todos os testes
uv run pytest

# Com coverage
uv run pytest --cov=app --cov-report=html

# Testes especificos
uv run pytest tests/test_tools.py -v

# Testes com keyword
uv run pytest -k "calculate" -v

# Ou via Make
make test
```

---

## Servidor de Desenvolvimento

```bash
# Iniciar servidor com hot-reload
uv run uvicorn app.main:app --reload

# Ou via Make
make dev
```

---

## Troubleshooting

### Problemas Comuns

| Problema | Causa | Solucao |
|----------|-------|---------|
| API Key nao encontrada | Variavel de ambiente ausente | Verificar `.env` e `app/config.py` |
| 401 em endpoints | JWT incorreto ou expirado | Verificar `excluded_route_paths` em `app/auth.py` |
| Tool nao chamada pelo LLM | Docstring inadequada | Melhorar descricao da tool |
| Memoria nao persiste | Redis nao configurado | Configurar `REDIS_URL` |
| Rate limit atingido | Muitas requisicoes | Ajustar `RATE_LIMIT_REQUESTS_PER_MINUTE` |
| Historico nao funciona | `conversation_id` ausente | Passar `conversation_id` na requisicao |
| Tool retorna erro | Excecao nao tratada | Usar `RetryAgentRun` para feedback ao LLM |
| Circuit breaker aberto | Falhas consecutivas | Verificar logs e `circuit_breaker_state` no `/metrics` |

### Debug de Tools

```python
import logging
from app.runtime import RunContext, RetryAgentRun, tool

logger = logging.getLogger(__name__)

@tool
def minha_tool(run_context: RunContext, param: str) -> str:
    """Tool com logging para debug."""
    logger.info(f"Tool chamada com: {param}")
    logger.debug(f"Session state: {run_context.session_state}")

    try:
        resultado = processar(param)
        logger.info(f"Resultado: {resultado}")
        return resultado
    except Exception as e:
        logger.error(f"Erro na tool: {e}")
        raise RetryAgentRun(f"Erro: {e}. Tente com outros parametros.")
```

### Logs em Desenvolvimento

```bash
# Variaveis de ambiente para logs detalhados
LOG_LEVEL=DEBUG
LOG_FORMAT=text
```

O formato `text` eh mais legivel para desenvolvimento:

```
2025-01-15 10:30:00 | DEBUG    | [abc12345] app.agent_loop | Starting agent loop
2025-01-15 10:30:01 | INFO     | [abc12345] app.runtime | Tool "calculate" executed in 5ms
```

Para producao, use `LOG_FORMAT=json` para logs estruturados compativeis com ferramentas de agregacao (ELK, Loki, etc.).

### Verificando Configuracao

```python
from app.config import settings

print(f"MODULE_ID: {settings.MODULE_ID}")
print(f"AUTH_ENABLED: {settings.AUTH_ENABLED}")
print(f"REDIS_URL: {'OK' if settings.REDIS_URL else 'Nao configurado'}")
print(f"ANTHROPIC_API_KEY: {'OK' if settings.ANTHROPIC_API_KEY else 'Nao configurado'}")
print(f"LANGFUSE_ENABLED: {settings.LANGFUSE_ENABLED}")
print(f"METRICS_ENABLED: {settings.METRICS_ENABLED}")
```

### Verificando Metricas

```bash
# Acessar metricas Prometheus diretamente
curl http://localhost:8000/metrics

# Filtrar metricas do agente
curl -s http://localhost:8000/metrics | grep agent_
```

---

## Profiling

O modulo `app/profiling.py` permite identificar gargalos de performance em operacoes assincronas.

### Decorator para Funcoes

```python
from app.profiling import profile_async_function

@profile_async_function(log_slow_threshold_ms=500)
async def buscar_historico(conversation_id: str):
    """Emite warning se ultrapassar 500ms."""
    return await redis.lrange(f"history:{conversation_id}", 0, -1)
```

### Context Manager

```python
from app.profiling import profile_async

async def processar_requisicao():
    async with profile_async("llm_call", log_slow_threshold_ms=5000):
        response = await litellm.acompletion(...)
```

### Consultando Estatisticas

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/profiling
```

Retorna estatisticas agregadas (count, mean, min, max, p50, p95, p99) para cada operacao rastreada.

---

## Padroes de Arquitetura

### Runtime Proprio (app/runtime.py)

O projeto usa um runtime proprio em vez de um framework de agentes. Os componentes principais sao:

```python
from app.runtime import (
    RunContext,        # Contexto passado para tools durante execucao
    RetryAgentRun,     # Excecao: envia feedback ao LLM e continua o loop
    StopAgentRun,      # Excecao: para o agent loop imediatamente
    tool,              # Decorator para registrar tools
    ToolRegistry,      # Registro e execucao de tools
)
```

### Criando uma Nova Tool

Cada tool fica em seu proprio arquivo em `app/tools/`:

```python
# app/tools/minha_tool.py
"""Tool: minha_tool -- Descricao breve."""
from app.runtime import tool, RunContext, RetryAgentRun

@tool
def minha_tool(run_context: RunContext, parametro: str) -> str:
    """Descricao que o LLM usa para decidir quando chamar esta tool."""
    if not valido(parametro):
        raise RetryAgentRun("Parametro invalido. Tente com outro valor.")

    run_context.session_state["ultimo_resultado"] = resultado
    return resultado
```

Registre em `app/tools/__init__.py` (re-export) e em `app/agent.py` dentro de `get_tools_registry()`.

### Factory Pattern para Tools

```python
# app/tools/factory.py
from typing import List, Callable


def get_tools_for_role(role: str) -> List[Callable]:
    """Retorna tools baseado no papel do usuario."""
    base_tools = [get_current_time, calculate]

    if role == "admin":
        return base_tools + [admin_action, delete_resource]
    elif role == "analyst":
        return base_tools + [query_database, generate_report]
    else:
        return base_tools
```

### Dependency Injection via RunContext

```python
from app.runtime import RunContext, tool


@tool
def query_data(run_context: RunContext, query: str) -> str:
    """Consulta dados usando servicos disponveis no contexto."""
    # O session_state pode carregar dependencias configuradas no startup
    cache = run_context.session_state.get("cache")

    cached = cache.get(f"query:{query}") if cache else None
    if cached:
        return cached

    result = executar_query(query)
    if cache:
        cache.set(f"query:{query}", result)
    return str(result)
```

---

## Comandos Make

```bash
# Desenvolvimento
make install          # Instalar dependencias de producao
make dev              # Iniciar servidor de desenvolvimento
make test             # Rodar testes
make lint             # Verificar codigo
make format           # Formatar codigo

# Docker
make docker-build     # Build da imagem
make up               # Subir servicos
make down             # Parar servicos
make logs             # Ver logs

# Migrations
make migrate          # Rodar migrations Alembic
make migrate-down     # Rollback ultima migration
make migrate-new      # Criar nova migration

# Limpeza
make clean            # Remover arquivos de cache
```

---

## Checklists de Implementacao

### Novo Modulo

- [ ] Definir `MODULE_ID` unico
- [ ] Configurar variaveis de ambiente (`.env`)
- [ ] Implementar ferramentas necessarias em `app/tools/`
- [ ] Configurar instrucoes do agente em `app/agent.py`
- [ ] Testar endpoints `/metadata`, `/run`, `/run_debug`
- [ ] Documentar ferramentas em `/metadata`
- [ ] Configurar Langfuse para gestao de prompts (opcional)
- [ ] Configurar OpenTelemetry para tracing (opcional)
- [ ] Implementar testes automatizados
- [ ] Verificar metricas em `/metrics`

### Nova Ferramenta

- [ ] Criar arquivo `app/tools/minha_tool.py`
- [ ] Usar decorator `@tool` de `app.runtime`
- [ ] Adicionar docstring descritiva (o LLM usa para decidir quando chamar)
- [ ] Adicionar type hints em todos os parametros
- [ ] Implementar tratamento de erros com `RetryAgentRun` / `StopAgentRun`
- [ ] Registrar em `app/tools/__init__.py`
- [ ] Adicionar ao registry em `app/agent.py` (`get_tools_registry()`)
- [ ] Escrever testes unitarios em `tests/test_tools.py`
- [ ] Atualizar `/metadata` tools_exposed

### Memoria Consolidada

- [ ] Configurar `REDIS_URL` para persistencia
- [ ] Habilitar `MEMORY_CONSOLIDATION_ENABLED=true`
- [ ] Definir `MEMORY_WINDOW` (numero de mensagens antes de consolidar)
- [ ] Escolher modelo barato para consolidacao (`MEMORY_CONSOLIDATION_MODEL`)
- [ ] Testar que fatos consolidados aparecem no system prompt

---

## Referencias

- [Pytest Documentation](https://docs.pytest.org)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [LiteLLM Documentation](https://docs.litellm.ai/)
- [Langfuse Documentation](https://langfuse.com/docs)
- [Prometheus Client Python](https://github.com/prometheus/client_python)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
