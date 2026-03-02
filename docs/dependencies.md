# Dependencies (Injecao de Dependencias)

Injecao de dependencias permite fornecer dados e servicos externos que tools podem acessar em runtime atraves do `RunContext`.

---

## Abordagem

No template atual, dependencias sao injetadas via:
1. **`RunContext.session_state`** — para dados da sessao
2. **Modulos Python** — para servicos (importacao direta)
3. **Settings** — para configuracao via `app/config.py`

---

## Usando RunContext

O `RunContext` de `app/runtime.py` fornece acesso ao estado da sessao:

```python
from app.runtime import tool, RunContext


@tool
def buscar_perfil(run_context: RunContext) -> str:
    """Busca o perfil do usuario na sessao."""
    dados = run_context.session_state.get('dados_cliente', {})
    nome = dados.get('nome', 'Desconhecido')
    return f"Usuario: {nome}"
```

O `run_context` e injetado automaticamente pelo `ToolRegistry` — o LLM nao vê esse parametro.

---

## Padrao de Servicos

Para servicos externos (APIs, bancos de dados, cache), use importacao direta:

```python
# app/tools/consulta_api.py

from app.runtime import tool, RetryAgentRun
from app.config import settings


@tool
def consultar_api(endpoint: str) -> str:
    """Consulta dados de uma API externa.

    Args:
        endpoint: Caminho do endpoint (ex: /usuarios/123).
    """
    import httpx

    try:
        resp = httpx.get(
            f"{settings.API_BASE_URL}{endpoint}",
            headers={"Authorization": f"Bearer {settings.API_TOKEN}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return str(resp.json())
    except httpx.HTTPError as e:
        raise RetryAgentRun(f"Erro na API: {e}")
```

### Servicos com Cache

```python
# app/tools/dados_cache.py

from app.runtime import tool, RunContext


@tool
def buscar_dados(run_context: RunContext, query: str) -> str:
    """Busca dados com cache no session state.

    Args:
        query: Termo de busca.
    """
    cache = run_context.session_state.setdefault('cache', {})

    if query in cache:
        return cache[query]

    # Buscar dados (API, banco, etc.)
    resultado = _fetch_dados(query)

    cache[query] = resultado
    return resultado


def _fetch_dados(query: str) -> str:
    """Implementacao real da busca."""
    return f"Resultado para: {query}"
```

### Servicos com Redis

```python
# app/tools/cache_redis.py

from app.runtime import tool
from app.storage import get_redis


@tool
async def buscar_com_cache(chave: str) -> str:
    """Busca dados com cache Redis.

    Args:
        chave: Chave de busca.
    """
    redis = await get_redis()
    if redis:
        cached = await redis.get(f"cache:{chave}")
        if cached:
            return cached

    resultado = _processar(chave)

    if redis:
        await redis.set(f"cache:{chave}", resultado, ex=3600)

    return resultado
```

---

## Configuracao via Settings

Use `app/config.py` para configuracoes injetaveis:

```python
# app/config.py
class Settings(BaseSettings):
    API_BASE_URL: str = 'https://api.exemplo.com'
    API_TOKEN: str = ''
    MAX_RESULTS: int = 10

# Na tool
from app.config import settings

@tool
def buscar(query: str) -> str:
    """Busca com limite configuravel."""
    return _search(query, limit=settings.MAX_RESULTS)
```

---

## Comparacao de Abordagens

| Mecanismo | Quando Usar |
|-----------|-------------|
| `settings.KEY` em `app/config.py` | Configuracoes globais via variaveis de ambiente |
| `run_context.session_state["key"]` | Dados que mudam por sessao/conversa |
| Import direto de modulos | Servicos e funcoes utilitarias |
| `formatar_contexto_completo()` | Injecao automatica de estado no prompt |

---

## Boas Praticas

| Pratica | Descricao |
|---------|-----------|
| **Config via Settings** | Use `app/config.py` para valores configuraveis via env vars |
| **Session state para dados de sessao** | Use `run_context.session_state` para dados que mudam por conversa |
| **Import direto para servicos** | Importe modulos de servico diretamente nas tools |
| **Lazy imports** | Para dependencias pesadas, use import dentro da funcao |
| **Cache no session state** | Evite chamadas repetidas cacheando no `session_state` |
