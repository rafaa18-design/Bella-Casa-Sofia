# Clientes HTTP para a API

Este documento mostra como consumir a API do agente usando clientes HTTP padrao (`httpx`, `requests`). Nao existe SDK proprietario -- a comunicacao e feita via REST com autenticacao JWT.

---

## Visao Geral

| Conceito | Descricao |
|----------|-----------|
| **Protocolo** | REST sobre HTTP/HTTPS |
| **Autenticacao** | JWT Bearer token |
| **Formato** | JSON (request e response) |
| **Endpoints principais** | `/run`, `/run_debug`, `/metadata` |
| **Bibliotecas recomendadas** | `httpx` (async/sync), `requests` (sync) |

---

## Autenticacao

Antes de chamar os endpoints do agente, e necessario obter um token JWT via login.

### Login com httpx

```python
import httpx

BASE_URL = "http://localhost:8000"

def login(username: str, password: str) -> str:
    """Fazer login e retornar o access_token."""
    response = httpx.post(
        f"{BASE_URL}/auth/login",
        params={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["access_token"]

token = login("admin", "minha_senha")
```

### Login com requests

```python
import requests

BASE_URL = "http://localhost:8000"

def login(username: str, password: str) -> str:
    """Fazer login e retornar o access_token."""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        params={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["access_token"]

token = login("admin", "minha_senha")
```

### Login com curl

```bash
# Obter token
TOKEN=$(curl -s -X POST \
  "http://localhost:8000/auth/login?username=admin&password=minha_senha" \
  | jq -r '.access_token')

echo $TOKEN
```

---

## Endpoint `/metadata` (GET)

Retorna as capacidades e configuracao do modulo. Nao requer body.

### Exemplo com httpx

```python
import httpx

def get_metadata(token: str) -> dict:
    """Obter metadata do modulo."""
    response = httpx.get(
        f"{BASE_URL}/metadata",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return response.json()

metadata = get_metadata(token)
print(f"Modulo: {metadata['module_id']} v{metadata['version']}")
print(f"Tools disponiveis: {[t['name'] for t in metadata.get('tools_exposed', [])]}")
print(f"Modelos suportados: {metadata.get('models_supported', [])}")
```

### Exemplo com curl

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/metadata | jq
```

### Resposta esperada

```json
{
  "module_id": "meu-agente",
  "version": "1.0.0",
  "description": "Asani AI Agent",
  "capabilities": {
    "supports_multi_stage": false,
    "supports_dynamic_system_prompt": true,
    "supports_cross_model": true,
    "supports_jailbreak_tests": true
  },
  "pipeline": {
    "is_monolithic": true,
    "stages": [{"id": "main", "type": "agent", "model_configurable": true}]
  },
  "tools_exposed": [
    {"name": "listar_servicos", "description": "Lista os servicos disponiveis"},
    {"name": "verificar_disponibilidade", "description": "Verifica horarios disponiveis"}
  ],
  "input_types": {
    "supported_types": ["text", "image", "audio"],
    "allowed_formats": {"image": ["jpeg", "jpg", "png", "webp"], "audio": ["mp3", "wav", "ogg"]}
  },
  "models_supported": ["claude-sonnet-4-20250514", "gpt-4o"]
}
```

---

## Endpoint `/run` (POST)

Executa o agente e retorna a resposta final. Este e o endpoint principal para uso em producao.

### Request Body

```json
{
  "input": [
    {"type": "text", "content": "Mensagem do usuario"}
  ],
  "conversation_id": "conv-123",
  "model": null
}
```

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `input` | `list[InputItem]` | Sim | Lista de itens (texto, imagem, audio) |
| `conversation_id` | `str` | Sim | Identificador da conversa (para historico) |
| `model` | `str \| null` | Nao | Override do modelo LLM |

### InputItem

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `type` | `"text" \| "image" \| "audio" \| "document" \| "video"` | Tipo do conteudo |
| `content` | `str` | Texto ou conteudo em base64 |
| `filename` | `str \| null` | Nome do arquivo original |
| `mime_type` | `str \| null` | MIME type (ex: `image/png`) |

### Exemplo com httpx (sincrono)

```python
import httpx

def run_agent(token: str, message: str, conversation_id: str, model: str | None = None) -> dict:
    """Executar o agente com uma mensagem de texto."""
    response = httpx.post(
        f"{BASE_URL}/run",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "input": [{"type": "text", "content": message}],
            "conversation_id": conversation_id,
            "model": model,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()

# Uso
result = run_agent(token, "Quais servicos voces oferecem?", "conv-001")
print(result["final_output"]["message"])
```

### Exemplo com httpx (assincrono)

```python
import httpx
import asyncio

async def run_agent_async(
    token: str, message: str, conversation_id: str
) -> dict:
    """Executar o agente de forma assincrona."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BASE_URL}/run",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "input": [{"type": "text", "content": message}],
                "conversation_id": conversation_id,
            },
        )
        response.raise_for_status()
        return response.json()

# Uso
result = asyncio.run(run_agent_async(token, "Ola!", "conv-002"))
print(result["final_output"]["message"])
```

### Exemplo com requests

```python
import requests

def run_agent(token: str, message: str, conversation_id: str) -> dict:
    """Executar o agente com requests."""
    response = requests.post(
        f"{BASE_URL}/run",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "input": [{"type": "text", "content": message}],
            "conversation_id": conversation_id,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()

result = run_agent(token, "Quais servicos voces oferecem?", "conv-001")
print(result["final_output"]["message"])
```

### Exemplo com curl

```bash
curl -s -X POST http://localhost:8000/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"type": "text", "content": "Quais servicos voces oferecem?"}],
    "conversation_id": "conv-001"
  }' | jq
```

### Resposta esperada

```json
{
  "conversation_id": "conv-001",
  "final_output": {
    "message": "Oferecemos os seguintes servicos: ...",
    "state": {"cliente_nome": "Joao"},
    "actions_taken": [
      {"tool": "listar_servicos", "success": true, "error": null}
    ]
  },
  "metrics": {
    "latency_ms": 2340.5,
    "tokens_used": 1523,
    "cost_estimate": null
  }
}
```

---

## Endpoint `/run_debug` (POST)

Mesmo formato de request que `/run`, mas retorna a trajetoria completa para observabilidade e depuracao.

### Exemplo com httpx

```python
def run_debug(token: str, message: str, conversation_id: str) -> dict:
    """Executar o agente em modo debug."""
    response = httpx.post(
        f"{BASE_URL}/run_debug",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "input": [{"type": "text", "content": message}],
            "conversation_id": conversation_id,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()

result = run_debug(token, "Agende uma consulta para amanha", "conv-debug-001")

# Resposta do agente
print(result["final_output"]["message"])

# Trajetoria detalhada
for stage in result["trajectory"]:
    print(f"Stage: {stage['stage_id']} ({stage['type']})")
    print(f"  Latencia: {stage['latency_ms']:.1f}ms")
    if stage.get("llm_calls"):
        for call in stage["llm_calls"]:
            print(f"  Modelo: {call['model']}")
            print(f"  Tokens: {call['input_tokens']} in / {call['output_tokens']} out")

# Metricas agregadas
metrics = result["metrics"]
print(f"Latencia total: {metrics['total_latency_ms']:.1f}ms")
print(f"Chamadas LLM: {metrics['llm_calls']}")
print(f"Tokens: {metrics['total_tokens']}")
```

### Resposta esperada

```json
{
  "conversation_id": "conv-debug-001",
  "final_output": {
    "message": "Consulta agendada para amanha as 14h.",
    "state": {"consulta_agendada": true},
    "actions_taken": [
      {"tool": "verificar_disponibilidade", "success": true},
      {"tool": "agendar_consulta", "success": true}
    ]
  },
  "trajectory": [
    {
      "stage_id": "main",
      "type": "agent",
      "sequence": 1,
      "prompt_debug": {
        "final_system_prompt_used": "Voce e um assistente..."
      },
      "llm_calls": [
        {"model": "claude-sonnet-4-20250514", "input_tokens": 1200, "output_tokens": 350}
      ],
      "latency_ms": 3200.5
    }
  ],
  "metrics": {
    "total_latency_ms": 3200.5,
    "total_tokens": {"input": 1200, "output": 350},
    "llm_calls": 1
  }
}
```

---

## Enviando Conteudo Multimodal

### Imagem (base64)

```python
import base64

with open("foto.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode("utf-8")

result = httpx.post(
    f"{BASE_URL}/run",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={
        "input": [
            {"type": "text", "content": "O que voce ve nesta imagem?"},
            {"type": "image", "content": image_b64, "mime_type": "image/jpeg"},
        ],
        "conversation_id": "conv-img-001",
    },
    timeout=60.0,
)
```

### Audio (base64)

```python
with open("audio.mp3", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode("utf-8")

result = httpx.post(
    f"{BASE_URL}/run",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={
        "input": [
            {"type": "audio", "content": audio_b64, "mime_type": "audio/mpeg"},
        ],
        "conversation_id": "conv-audio-001",
    },
    timeout=60.0,
)
```

---

## Cliente Completo (Classe Reutilizavel)

Exemplo de classe que encapsula toda a comunicacao com a API:

```python
import httpx
from dataclasses import dataclass


@dataclass
class AgentResult:
    """Resultado da execucao do agente."""
    message: str
    state: dict | None
    actions: list[dict] | None
    latency_ms: float
    tokens_used: int | None


class AgentClient:
    """Cliente para a API do agente."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        self._username = username
        self._password = password

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("Nao autenticado. Chame login() primeiro.")
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def login(self) -> str:
        """Autenticar e armazenar token."""
        response = httpx.post(
            f"{self.base_url}/auth/login",
            params={"username": self._username, "password": self._password},
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]
        return self.token

    def get_metadata(self) -> dict:
        """Obter metadata do modulo."""
        response = httpx.get(
            f"{self.base_url}/metadata",
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def run(
        self,
        message: str,
        conversation_id: str,
        model: str | None = None,
    ) -> AgentResult:
        """Executar o agente."""
        response = httpx.post(
            f"{self.base_url}/run",
            headers=self._headers(),
            json={
                "input": [{"type": "text", "content": message}],
                "conversation_id": conversation_id,
                "model": model,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()

        output = data["final_output"]
        metrics = data.get("metrics", {})

        return AgentResult(
            message=output["message"],
            state=output.get("state"),
            actions=output.get("actions_taken"),
            latency_ms=metrics.get("latency_ms", 0),
            tokens_used=metrics.get("tokens_used"),
        )

    def run_debug(
        self,
        message: str,
        conversation_id: str,
    ) -> dict:
        """Executar o agente em modo debug (retorna resposta completa)."""
        response = httpx.post(
            f"{self.base_url}/run_debug",
            headers=self._headers(),
            json={
                "input": [{"type": "text", "content": message}],
                "conversation_id": conversation_id,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()

    def health(self) -> dict:
        """Verificar status da API (nao requer autenticacao)."""
        response = httpx.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()


# Uso
client = AgentClient(
    base_url="http://localhost:8000",
    username="admin",
    password="minha_senha",
)
client.login()

# Verificar saude
print(client.health())

# Obter metadata
meta = client.get_metadata()
print(f"Modulo: {meta['module_id']}")

# Executar agente
result = client.run("Quais servicos estao disponiveis?", "conv-001")
print(f"Resposta: {result.message}")
print(f"Latencia: {result.latency_ms:.0f}ms")

# Conversa multi-turno (mesmo conversation_id)
result2 = client.run("E quais tem horario disponivel amanha?", "conv-001")
print(f"Resposta: {result2.message}")
```

---

## Tratamento de Erros

### Codigos HTTP

| Codigo | Significado | Acao recomendada |
|--------|-------------|-----------------|
| `200` | Sucesso | Processar resposta |
| `401` | Token ausente, expirado ou invalido | Refazer login |
| `403` | Scope insuficiente | Solicitar token com permissoes adequadas |
| `429` | Rate limit excedido | Aguardar `Retry-After` segundos |
| `500` | Erro interno | Tentar novamente com backoff |

### Exemplo com retry

```python
import time
import httpx

def run_with_retry(
    client: AgentClient,
    message: str,
    conversation_id: str,
    max_retries: int = 3,
) -> AgentResult:
    """Executar com retry automatico."""
    for attempt in range(max_retries):
        try:
            return client.run(message, conversation_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token expirado, refazer login
                client.login()
                continue
            elif e.response.status_code == 429:
                # Rate limit, aguardar
                retry_after = int(e.response.headers.get("Retry-After", "60"))
                time.sleep(retry_after)
                continue
            elif e.response.status_code >= 500:
                # Erro do servidor, backoff exponencial
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError(f"Falha apos {max_retries} tentativas")
```

---

## Headers de Rate Limit

Todas as respostas incluem headers informativos sobre o rate limit:

| Header | Descricao |
|--------|-----------|
| `X-RateLimit-Limit` | Maximo de requests por minuto |
| `X-RateLimit-Remaining` | Requests restantes na janela atual |
| `X-RateLimit-Reset` | Unix timestamp de quando a janela reseta |
| `Retry-After` | Segundos para aguardar (apenas em 429) |
