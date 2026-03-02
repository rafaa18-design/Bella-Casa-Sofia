# Guardrails (Validacao e Moderacao)

Guardrails sao mecanismos de seguranca que validam e moderam conteudo antes e depois do processamento pelo agente. Servem para bloquear inputs maliciosos, detectar PII, moderar conteudo e garantir que as respostas estejam dentro dos limites aceitaveis.

---

## Abordagem

Guardrails sao implementados diretamente na funcao `execute_agent()` em `app/main.py`, executando validacao antes e depois de `run_agent_loop()`.

---

## Como Implementar

### 1. Guardrail como Funcao de Validacao

Crie funcoes de validacao que lancam excecoes quando o conteudo e bloqueado:

```python
# app/guardrails.py

import re


class GuardrailError(Exception):
    """Erro lancado quando um guardrail bloqueia o conteudo."""
    def __init__(self, message: str, category: str = "blocked"):
        self.message = message
        self.category = category
        super().__init__(message)


def validar_pii(text: str) -> None:
    """Bloqueia input que contem dados pessoais identificaveis."""
    patterns = {
        "CPF": r'\d{3}\.\d{3}\.\d{3}-\d{2}',
        "Email": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        "Telefone": r'\(\d{2}\)\s?\d{4,5}-?\d{4}',
        "Cartao de Credito": r'\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}',
    }
    for pii_type, pattern in patterns.items():
        if re.search(pattern, text):
            raise GuardrailError(
                f"{pii_type} detectado no input. Remova dados pessoais.",
                category="pii",
            )


def validar_urls(text: str) -> None:
    """Bloqueia input que contem URLs."""
    url_pattern = r'https?://[^\s]+|www\.[^\s]+'
    if re.search(url_pattern, text):
        raise GuardrailError(
            "URLs nao sao permitidas no input.",
            category="url",
        )


def validar_tamanho(text: str, max_chars: int = 10000) -> None:
    """Bloqueia input que excede o tamanho maximo."""
    if len(text) > max_chars:
        raise GuardrailError(
            f"Input excede o limite de {max_chars} caracteres.",
            category="size",
        )
```

### 2. Integrar no Pipeline do Agente

Aplique guardrails em `execute_agent()` em `app/main.py`:

```python
# app/main.py (dentro de execute_agent)

from app.guardrails import GuardrailError, validar_pii, validar_urls, validar_tamanho

async def execute_agent(request, debug=False):
    text_message, images = parse_multimodal_input(request.input)

    # === GUARDRAILS DE INPUT ===
    try:
        validar_tamanho(text_message)
        validar_pii(text_message)
        validar_urls(text_message)
    except GuardrailError as e:
        return AgentRunResult(
            content=f"Input bloqueado: {e.message}",
            error=True,
        )

    # Execucao normal do agente
    response = await run_agent_loop(...)

    # === GUARDRAILS DE OUTPUT ===
    try:
        validar_pii(response.content)
    except GuardrailError:
        response.content = "A resposta foi bloqueada por conter dados sensiveis."

    return response
```

### 3. Guardrail como Tool (Alternativa)

Outra abordagem e criar uma tool de validacao que o proprio agente pode chamar:

```python
# app/tools/validar_conteudo.py

from app.runtime import tool, StopAgentRun


@tool
def validar_conteudo(texto: str, tipo: str = "geral") -> str:
    """Valida se o conteudo e apropriado antes de prosseguir.

    Args:
        texto: Conteudo a ser validado.
        tipo: Tipo de validacao (geral, pii, moderacao).
    """
    import re

    if tipo == "pii":
        if re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', texto):
            raise StopAgentRun("CPF detectado. Nao posso processar dados pessoais.")

    return "Conteudo validado com sucesso."
```

### 4. Moderacao via API Externa

Para moderacao mais sofisticada, use a API de moderacao da OpenAI ou similar:

```python
# app/guardrails.py

import litellm


async def moderar_conteudo(text: str) -> None:
    """Usa API de moderacao para verificar conteudo."""
    # Usar litellm para chamar a API de moderacao da OpenAI
    import openai
    client = openai.AsyncOpenAI()
    result = await client.moderations.create(input=text)

    if result.results[0].flagged:
        categories = [
            cat for cat, flagged
            in result.results[0].categories.__dict__.items()
            if flagged
        ]
        raise GuardrailError(
            f"Conteudo bloqueado por moderacao. Categorias: {', '.join(categories)}",
            category="moderation",
        )
```

---

## Resumo

| Componente | Descricao |
|------------|-----------|
| Validacao de input | Funcoes de validacao em `app/guardrails.py` |
| Pre-validacao | Validacao antes de `run_agent_loop()` em `execute_agent()` |
| Pos-validacao | Validacao apos `run_agent_loop()` em `execute_agent()` |
| Excecoes de controle | `GuardrailError` customizado ou `StopAgentRun` |
| Moderacao externa | Chamada direta a API de moderacao da OpenAI |
