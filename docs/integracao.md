# Integracoes (Tools, Extensoes e Servicos Externos)

Este documento descreve como integrar o agente com servicos e sistemas externos. Toda integracao e feita via **tools customizadas** registradas no `ToolRegistry`.

---

## Visao Geral

| Conceito | Descricao |
|----------|-----------|
| **`@tool`** | Decorator que converte uma funcao em `ToolDefinition` |
| **`ToolRegistry`** | Registro central de tools com execucao e definicoes OpenAI-compativeis |
| **`RunContext`** | Contexto de execucao injetado nas tools (session state, IDs) |
| **`RetryAgentRun`** | Excecao para enviar feedback ao LLM e re-tentar |
| **`StopAgentRun`** | Excecao para parar o agent loop imediatamente |

Todos esses componentes estao definidos em `app/runtime.py`.

---

## Criando Tools Customizadas

### Estrutura de Arquivos

Cada tool fica em seu proprio arquivo dentro de `app/tools/`:

```
app/tools/
├── __init__.py           # Re-exports de todas as tools
├── _helpers.py           # Funcoes auxiliares compartilhadas
├── _mock_data.py         # Dados mockados (apenas para dev)
├── servicos.py           # Tool: listar_servicos
├── disponibilidade.py    # Tool: verificar_disponibilidade
├── agendamento.py        # Tool: agendar_consulta
└── minha_nova_tool.py    # Sua nova tool
```

### Tool Basica

```python
"""Tool: consultar_cep -- Consulta endereco por CEP."""
from app.runtime import tool

@tool
def consultar_cep(cep: str) -> str:
    """Consulta endereco completo a partir de um CEP.

    Args:
        cep: CEP no formato 00000-000 ou 00000000.
    """
    import httpx

    cep_limpo = cep.replace("-", "").strip()
    response = httpx.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=10.0)
    response.raise_for_status()

    data = response.json()
    if data.get("erro"):
        return f"CEP {cep} nao encontrado."

    return (
        f"Endereco: {data['logradouro']}, {data['bairro']}, "
        f"{data['localidade']}/{data['uf']} - CEP {data['cep']}"
    )
```

### Tool com RunContext

Use `RunContext` quando a tool precisa acessar ou modificar o estado da sessao:

```python
"""Tool: salvar_endereco -- Salva endereco no contexto da sessao."""
from app.runtime import tool, RunContext

@tool
def salvar_endereco(run_context: RunContext, endereco: str, tipo: str = "residencial") -> str:
    """Salva um endereco no contexto da sessao.

    Args:
        run_context: Contexto de execucao (injetado automaticamente).
        endereco: Endereco completo.
        tipo: Tipo do endereco (residencial, comercial).
    """
    enderecos = run_context.session_state.get("enderecos", [])
    enderecos.append({"endereco": endereco, "tipo": tipo})
    run_context.session_state["enderecos"] = enderecos

    return f"Endereco {tipo} salvo: {endereco}"
```

O parametro `run_context` e **automaticamente filtrado** do JSON Schema enviado ao LLM -- o modelo nunca o ve. O `ToolRegistry` injeta o `RunContext` em tempo de execucao.

### Tool com Validacao (RetryAgentRun)

Use `RetryAgentRun` para enviar feedback ao LLM quando os parametros estao incorretos:

```python
"""Tool: validar_cpf -- Valida um CPF."""
from app.runtime import tool, RetryAgentRun

@tool
def validar_cpf(cpf: str) -> str:
    """Valida um numero de CPF brasileiro.

    Args:
        cpf: CPF com 11 digitos.
    """
    cpf_limpo = cpf.replace(".", "").replace("-", "").strip()

    if len(cpf_limpo) != 11 or not cpf_limpo.isdigit():
        raise RetryAgentRun(
            f"CPF '{cpf}' invalido. Fornecer 11 digitos numericos (ex: 123.456.789-00)."
        )

    # Logica de validacao...
    return f"CPF {cpf_limpo} e valido."
```

Quando `RetryAgentRun` e lancada, o agent loop envia a mensagem de erro como resultado da tool de volta ao LLM, que pode corrigir e chamar novamente.

### Tool com Parada (StopAgentRun)

Use `StopAgentRun` para encerrar o agent loop imediatamente:

```python
"""Tool: encerrar_atendimento -- Encerra o atendimento."""
from app.runtime import tool, StopAgentRun

@tool
def encerrar_atendimento(motivo: str = "finalizado") -> str:
    """Encerra o atendimento atual.

    Args:
        motivo: Motivo do encerramento.
    """
    raise StopAgentRun(f"Atendimento encerrado: {motivo}. Obrigado!")
```

### Tool Assincrona

Tools podem ser `async` -- o `ToolRegistry` detecta automaticamente:

```python
"""Tool: buscar_clima -- Consulta previsao do tempo."""
import httpx
from app.runtime import tool

@tool
async def buscar_clima(cidade: str) -> str:
    """Consulta a previsao do tempo para uma cidade.

    Args:
        cidade: Nome da cidade.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.weatherapi.com/v1/current.json",
            params={"key": "SUA_API_KEY", "q": cidade, "lang": "pt"},
        )
        response.raise_for_status()

    data = response.json()
    current = data["current"]
    return (
        f"Clima em {cidade}: {current['condition']['text']}, "
        f"{current['temp_c']}C, umidade {current['humidity']}%"
    )
```

---

## Registrando Tools

Apos criar a tool, registre-a em dois lugares:

### 1. Re-export em `app/tools/__init__.py`

```python
from app.tools.minha_nova_tool import consultar_cep
from app.tools.endereco import salvar_endereco
```

### 2. Adicionar ao registro em `app/agent.py`

```python
from app.tools import consultar_cep, salvar_endereco

def get_tools_registry() -> ToolRegistry:
    registry = ToolRegistry()

    all_tools = [
        # ... tools existentes ...
        consultar_cep,
        salvar_endereco,
    ]

    for tool_def in all_tools:
        registry.register(tool_def)

    return registry
```

---

## Como o Sistema de Tools Funciona

### Fluxo Completo

```
1. get_tools_registry() cria o ToolRegistry com todas as tools
2. registry.get_definitions() gera JSON Schema OpenAI-compativel
3. litellm.acompletion() recebe as definicoes como parametro `tools`
4. LLM decide chamar uma tool -> retorna tool_calls
5. Agent loop executa registry.execute(name, args, run_context)
6. ToolRegistry injeta RunContext se a funcao aceita `run_context`
7. Resultado da tool e adicionado as messages como role='tool'
8. Loop continua ate o LLM responder sem tool_calls
```

### Decorator `@tool` em Detalhe

O decorator `@tool` converte a funcao em `ToolDefinition`:

```python
@dataclass
class ToolDefinition:
    name: str                    # Nome da funcao
    description: str             # Primeira linha da docstring
    parameters: dict[str, Any]   # JSON Schema dos parametros
    func: Callable               # Referencia a funcao original
```

Conversao de tipos Python para JSON Schema:

| Python | JSON Schema |
|--------|-------------|
| `str` | `"string"` |
| `int` | `"integer"` |
| `float` | `"number"` |
| `bool` | `"boolean"` |
| `list` | `"array"` |
| `dict` | `"object"` |
| `list[str]` | `{"type": "array", "items": {"type": "string"}}` |

Parametros sem valor padrao sao marcados como `required` no schema.

---

## Integracoes com Servicos Externos

### Padrao Recomendado: API Wrapper como Tool

Para integrar com qualquer servico externo, crie uma tool que encapsula a chamada:

```python
"""Tool: enviar_email -- Envia email via SendGrid."""
import httpx
from app.runtime import tool, RetryAgentRun
from app.config import settings

@tool
async def enviar_email(destinatario: str, assunto: str, corpo: str) -> str:
    """Envia um email para o destinatario.

    Args:
        destinatario: Email do destinatario.
        assunto: Assunto do email.
        corpo: Corpo do email em texto.
    """
    if "@" not in destinatario:
        raise RetryAgentRun("Email invalido. Fornecer um email valido com @.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [{"to": [{"email": destinatario}]}],
                "from": {"email": "noreply@empresa.com"},
                "subject": assunto,
                "content": [{"type": "text/plain", "value": corpo}],
            },
        )

    if response.status_code == 202:
        return f"Email enviado para {destinatario}."
    return f"Falha ao enviar email: {response.status_code} {response.text[:200]}"
```

### Integracao com Banco de Dados

```python
"""Tool: consultar_pedido -- Consulta pedido no banco de dados."""
from app.runtime import tool, RetryAgentRun

@tool
async def consultar_pedido(numero_pedido: str) -> str:
    """Consulta o status de um pedido pelo numero.

    Args:
        numero_pedido: Numero do pedido (ex: PED-12345).
    """
    if not numero_pedido.startswith("PED-"):
        raise RetryAgentRun("Numero do pedido deve comecar com PED- (ex: PED-12345).")

    # Usar SQLAlchemy, asyncpg, ou qualquer driver
    import asyncpg

    conn = await asyncpg.connect("postgresql://user:pass@localhost/db")
    try:
        row = await conn.fetchrow(
            "SELECT status, data_criacao, valor FROM pedidos WHERE numero = $1",
            numero_pedido,
        )
        if not row:
            return f"Pedido {numero_pedido} nao encontrado."

        return (
            f"Pedido {numero_pedido}: status={row['status']}, "
            f"data={row['data_criacao']}, valor=R${row['valor']:.2f}"
        )
    finally:
        await conn.close()
```

### Integracao com Filas (Redis/RabbitMQ)

```python
"""Tool: solicitar_processamento -- Envia tarefa para fila de processamento."""
from app.runtime import tool, RunContext

@tool
async def solicitar_processamento(run_context: RunContext, tipo: str, dados: str) -> str:
    """Solicita processamento assincrono de uma tarefa.

    Args:
        run_context: Contexto da sessao (injetado automaticamente).
        tipo: Tipo de processamento (relatorio, exportacao, analise).
        dados: Dados para processamento em formato texto.
    """
    import json
    from app.storage import get_redis

    redis = await get_redis()
    if not redis:
        return "Servico de filas indisponivel no momento."

    task_id = f"task:{run_context.session_id}:{tipo}"
    await redis.lpush("processing_queue", json.dumps({
        "task_id": task_id,
        "tipo": tipo,
        "dados": dados,
        "user_id": run_context.user_id,
    }))

    run_context.session_state["ultima_task"] = task_id

    return f"Tarefa {task_id} enviada para processamento. Voce sera notificado quando concluir."
```

---

## Avaliacao de Tools (Evals)

Para avaliar a qualidade das respostas do agente, voce pode criar testes que verificam se as tools sao chamadas corretamente:

```python
"""Testes de integracao para tools."""
import pytest
import httpx

BASE_URL = "http://localhost:8000"

@pytest.fixture
def token():
    """Obter token de autenticacao."""
    response = httpx.post(
        f"{BASE_URL}/auth/login",
        params={"username": "admin", "password": "senha"},
    )
    return response.json()["access_token"]

def test_listar_servicos(token):
    """Verificar se o agente lista servicos quando solicitado."""
    response = httpx.post(
        f"{BASE_URL}/run",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "input": [{"type": "text", "content": "Quais servicos voces oferecem?"}],
            "conversation_id": "test-eval-001",
        },
        timeout=60.0,
    )
    data = response.json()

    assert response.status_code == 200
    assert data["final_output"]["message"]  # Resposta nao vazia

    # Verificar que a tool correta foi chamada
    actions = data["final_output"].get("actions_taken", [])
    tool_names = [a["tool"] for a in actions]
    assert "listar_servicos" in tool_names

def test_conversa_multi_turno(token):
    """Verificar que o agente mantem contexto entre turnos."""
    conv_id = "test-multi-turn-001"

    # Turno 1
    r1 = httpx.post(
        f"{BASE_URL}/run",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "input": [{"type": "text", "content": "Meu nome e Maria"}],
            "conversation_id": conv_id,
        },
        timeout=60.0,
    )
    assert r1.status_code == 200

    # Turno 2 - deve lembrar o nome
    r2 = httpx.post(
        f"{BASE_URL}/run",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "input": [{"type": "text", "content": "Qual e meu nome?"}],
            "conversation_id": conv_id,
        },
        timeout=60.0,
    )
    assert "Maria" in r2.json()["final_output"]["message"]
```

---

## Boas Praticas para Integracoes

### 1. Docstrings Descritivas

A docstring e o que o LLM le para decidir quando e como usar a tool. Seja claro e especifico:

```python
@tool
def consultar_saldo(numero_conta: str) -> str:
    """Consulta o saldo atual de uma conta bancaria.

    Use esta tool quando o usuario perguntar sobre saldo, extrato ou
    valores disponiveis em conta. NAO use para transferencias.

    Args:
        numero_conta: Numero da conta com digito (ex: 12345-6).
    """
```

### 2. Validacao de Inputs com RetryAgentRun

Sempre valide os parametros e de feedback claro ao LLM:

```python
@tool
def agendar(data: str, horario: str) -> str:
    """Agenda um compromisso."""
    if not re.match(r"\d{4}-\d{2}-\d{2}", data):
        raise RetryAgentRun("Data deve estar no formato AAAA-MM-DD.")
    if not re.match(r"\d{2}:\d{2}", horario):
        raise RetryAgentRun("Horario deve estar no formato HH:MM.")
    # ...
```

### 3. Tratamento de Erros Robusto

Nunca deixe excecoes nao tratadas escaparem:

```python
@tool
async def buscar_api_externa(query: str) -> str:
    """Busca dados em API externa."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://api.exemplo.com/search?q={query}")
            response.raise_for_status()
            return response.json()["resultado"]
    except httpx.TimeoutException:
        return "Servico externo demorou para responder. Tente novamente."
    except httpx.HTTPStatusError as e:
        return f"Erro na API externa: {e.response.status_code}"
    except Exception as e:
        return f"Erro inesperado: {str(e)}"
```

### 4. Dados Mockados vs. Producao

O template inclui `app/tools/_mock_data.py` com dados ficticios para desenvolvimento. Em producao, substitua por integracoes reais:

```python
# DEV (mock)
from app.tools._mock_data import SERVICOS_MOCK

@tool
def listar_servicos() -> str:
    return json.dumps(SERVICOS_MOCK)

# PRODUCAO
@tool
async def listar_servicos() -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.interna.com/servicos")
        return response.text
```

### 5. Truncamento de Output

O agent loop trunca automaticamente outputs longos (configuravel via `TOOL_OUTPUT_MAX_CHARS`). Para tools que retornam grandes volumes de dados, faca resumo ou paginacao:

```python
@tool
def buscar_registros(filtro: str, pagina: int = 1) -> str:
    """Busca registros com paginacao.

    Args:
        filtro: Texto para filtrar resultados.
        pagina: Numero da pagina (comeca em 1, 10 por pagina).
    """
    # Retornar apenas 10 registros por vez
    offset = (pagina - 1) * 10
    registros = db.query(filtro, limit=10, offset=offset)
    return json.dumps({"registros": registros, "pagina": pagina, "total": db.count(filtro)})
```

---

## Arquivos Relevantes

| Arquivo | Responsabilidade |
|---------|-----------------|
| `app/runtime.py` | `@tool`, `ToolRegistry`, `RunContext`, `RetryAgentRun`, `StopAgentRun` |
| `app/agent.py` | `get_tools_registry()`, registro de todas as tools |
| `app/agent_loop.py` | Agent loop iterativo com execucao de tools |
| `app/tools/__init__.py` | Re-exports e funcao `formatar_contexto_completo()` |
| `app/tools/_helpers.py` | Funcoes auxiliares compartilhadas entre tools |
| `app/tools/_mock_data.py` | Dados mockados para desenvolvimento |
| `app/tools/*.py` | Uma tool por arquivo |
