# Tools (Ferramentas)

Este documento cobre a criacao de ferramentas, o decorator `@tool`, o `ToolRegistry`, acesso ao estado da sessao e tratamento de erros usando as exceptions do runtime customizado (`app/runtime.py`).

---

## Estrutura de Arquivos

Cada tool deve ficar em seu proprio arquivo dentro de `app/tools/`. O `__init__.py` re-exporta todas as tools.

```
app/tools/
├── __init__.py              # Re-exports de todas as tools + __all__
├── _mock_data.py            # Dados mockados compartilhados (APENAS para desenvolvimento)
├── _helpers.py              # Funcoes auxiliares (ensure_state, etc.)
├── formatar_contexto.py     # Helper para injecao de contexto (nao e tool)
├── listar_servicos.py       # Uma tool por arquivo
├── verificar_disponibilidade.py
├── agendar_consulta.py
├── cancelar_consulta.py
├── buscar_paciente.py
├── consultar_historico.py
├── consultar_convenios.py
├── calcular_orcamento.py
├── salvar_dados_cliente.py
├── salvar_preferencias.py
├── ver_contexto_sessao.py
└── obter_data_hora.py
```

> **Dados Mockados sao APENAS para Desenvolvimento**
>
> O arquivo `_mock_data.py` contem dados ficticios para permitir testes do pipeline
> completo (auth, metrics, tracing, state, etc.) sem dependencias externas.
> **Em producao, cada tool deve consultar APIs reais, bancos de dados ou servicos externos.**
> Remova `_mock_data.py` e atualize cada tool para usar a fonte de dados real,
> mantendo a mesma interface (assinatura e retorno).

---

## Criando uma Nova Tool

1. Crie um arquivo em `app/tools/minha_tool.py`:

```python
# app/tools/minha_tool.py
"""Tool: minha_tool -- Descricao breve."""

from app.runtime import tool, RetryAgentRun


@tool
def minha_tool(parametro: str) -> str:
    """Descricao da ferramenta para o LLM.

    O LLM usa esta docstring para decidir quando chamar a tool.
    Seja claro sobre quando e como usar.

    Args:
        parametro: Descricao do parametro.

    Returns:
        Resultado formatado.
    """
    if not parametro:
        raise RetryAgentRun("Parametro obrigatorio. Informe o valor.")
    return f"Resultado: {parametro}"
```

O decorator `@tool` converte a funcao em um `ToolDefinition`, extraindo:

- **Nome**: `func.__name__`
- **Descricao**: Primeira linha da docstring
- **Parametros**: JSON Schema gerado a partir da assinatura (type hints)
- O parametro `run_context` (se presente) e filtrado do schema automaticamente

2. Registre no `app/tools/__init__.py`:

```python
from app.tools.minha_tool import minha_tool

__all__ = [
    # ... tools existentes
    "minha_tool",
]
```

3. Adicione a lista de tools em `app/agent.py`, dentro de `get_tools_registry()`:

```python
from app.tools import minha_tool

def get_tools_registry() -> ToolRegistry:
    registry = ToolRegistry()

    all_tools = [
        # ... tools existentes
        minha_tool,
    ]

    for tool_def in all_tools:
        registry.register(tool_def)

    return registry
```

---

## Decorator @tool

O decorator `@tool` esta definido em `app/runtime.py`. Ele converte uma funcao Python em um `ToolDefinition` compativel com o formato OpenAI de tool calling.

### Como Funciona

```python
from app.runtime import tool

@tool
def buscar_clima(cidade: str) -> str:
    """Busca o clima atual de uma cidade.

    Args:
        cidade: Nome da cidade.
    """
    return f"O clima em {cidade} esta ensolarado, 25C."
```

O decorator gera automaticamente o seguinte JSON Schema para o LLM:

```json
{
    "type": "function",
    "function": {
        "name": "buscar_clima",
        "description": "Busca o clima atual de uma cidade.",
        "parameters": {
            "type": "object",
            "properties": {
                "cidade": {"type": "string"}
            },
            "required": ["cidade"]
        }
    }
}
```

### ToolDefinition

O resultado do decorator e um `ToolDefinition` (dataclass):

```python
@dataclass
class ToolDefinition:
    name: str                    # Nome da funcao
    description: str             # Primeira linha da docstring
    parameters: dict[str, Any]   # JSON Schema dos parametros
    func: Callable               # Referencia a funcao original
```

### Mapeamento de Tipos

O decorator converte type hints Python para tipos JSON Schema:

| Python    | JSON Schema |
|-----------|-------------|
| `str`     | `string`    |
| `int`     | `integer`   |
| `float`   | `number`    |
| `bool`    | `boolean`   |
| `list`    | `array`     |
| `dict`    | `object`    |

Parametros sem valor default sao marcados como `required`. Parametros com valor default incluem o default no schema.

---

## ToolRegistry

O `ToolRegistry` em `app/runtime.py` gerencia o registro e a execucao das tools. Ele e configurado em `app/agent.py:get_tools_registry()`.

### Interface

```python
class ToolRegistry:
    def register(self, tool_def: ToolDefinition) -> None:
        """Registra uma ToolDefinition."""

    def get_definitions(self) -> list[dict[str, Any]]:
        """Retorna definicoes no formato OpenAI para litellm."""

    async def execute(
        self,
        name: str,
        args: dict[str, Any],
        run_context: RunContext,
    ) -> str:
        """Executa uma tool pelo nome, injetando RunContext se necessario."""
```

### Comportamento da Execucao

- O `ToolRegistry.execute()` verifica se a funcao possui o parametro `run_context` na assinatura e, se sim, injeta-o automaticamente
- Suporta funcoes sincronas e assincronas
- Propaga `RetryAgentRun` e `StopAgentRun` para o agent loop
- Qualquer outra excecao e capturada e retornada como string de erro

---

## Acessando RunContext

O `RunContext` (definido em `app/runtime.py`) fornece acesso ao estado da sessao. Para usa-lo, basta declarar `run_context: RunContext` como primeiro parametro da tool -- ele sera injetado automaticamente pelo `ToolRegistry` e **nao aparece** no schema enviado ao LLM.

```python
from app.runtime import tool, RunContext
from app.tools._helpers import ensure_state


@tool
def salvar_nota(run_context: RunContext, nota: str) -> str:
    """Salva uma anotacao na sessao atual.

    Args:
        nota: Texto da anotacao.

    Returns:
        Confirmacao.
    """
    state = ensure_state(run_context)
    if "notas" not in state:
        state["notas"] = []
    state["notas"].append(nota)
    return f"Nota salva: {nota}"
```

### Atributos do RunContext

```python
@dataclass
class RunContext:
    session_state: dict[str, Any]   # Estado da sessao (leitura/escrita)
    session_id: str | None          # ID da sessao atual
    user_id: str | None             # ID do usuario
```

### Exemplo Completo com Estado

```python
from app.runtime import tool, RunContext
from app.tools._helpers import ensure_state


@tool
def adicionar_item(run_context: RunContext, item: str) -> str:
    """Adiciona item a lista de compras.

    Args:
        item: Item para adicionar.
    """
    state = ensure_state(run_context)

    if "lista" not in state:
        state["lista"] = []

    state["lista"].append(item)
    return f"'{item}' adicionado. Lista: {state['lista']}"
```

---

## Helpers e Dados Compartilhados

- **`_helpers.py`**: Funcoes auxiliares usadas por multiplas tools (ex: `ensure_state`, geradores de ID)
- **`_mock_data.py`**: Dados de desenvolvimento. Em producao, remova e substitua por dados reais
- **`formatar_contexto.py`**: Formatacao de state para injecao no prompt (usado por `main.py`, nao e tool)

A funcao `ensure_state` e um padrao comum para garantir que o `session_state` existe:

```python
from app.runtime import RunContext


def ensure_state(run_context: RunContext) -> dict:
    """Garante que o session_state existe e retorna."""
    if not run_context.session_state:
        run_context.session_state = {}
    return run_context.session_state
```

---

## Truncamento de Saida

O resultado de cada tool e truncado antes de ser enviado de volta ao LLM. Isso previne que saidas muito longas estourem a janela de contexto.

- O limite padrao e definido por `TOOL_OUTPUT_MAX_CHARS` no `app/config.py` (default: **500** caracteres)
- Saidas que excedem o limite sao cortadas com um indicador: `... [truncated, N total chars]`

Tenha isso em mente ao projetar o retorno das suas tools. Prefira retornar informacao concisa e relevante.

---

## Error Handling com Exceptions

O runtime customizado fornece duas exceptions para controlar o fluxo do agent loop. Ambas sao importadas de `app.runtime`.

| Exception        | Comportamento                                   | Quando Usar                        |
|------------------|--------------------------------------------------|------------------------------------|
| `RetryAgentRun`  | Envia feedback ao modelo, continua execucao      | Validacao, requisitos nao atendidos |
| `StopAgentRun`   | Para o loop de tool calls, finaliza a execucao   | Condicao critica atingida           |

### RetryAgentRun

Permite fornecer feedback ao LLM para que ele ajuste a chamada ou o comportamento. A mensagem e enviada como resultado da tool (prefixada com `Error: `), e o loop continua normalmente.

```python
from app.runtime import tool, RetryAgentRun, RunContext
from app.tools._helpers import ensure_state


@tool
def add_item(run_context: RunContext, item: str) -> str:
    """Adiciona item a lista de compras."""
    state = ensure_state(run_context)

    if "shopping_list" not in state:
        state["shopping_list"] = []

    state["shopping_list"].append(item)
    total = len(state["shopping_list"])

    if total < 3:
        raise RetryAgentRun(
            f"Shopping list: {state['shopping_list']}. "
            f"Minimo 3 itens. Adicione mais {3 - total}."
        )

    return f"Lista de compras: {state['shopping_list']}"
```

### Casos de Uso do RetryAgentRun

```python
from app.runtime import tool, RetryAgentRun, RunContext
from app.tools._helpers import ensure_state


# Validacao de Input
@tool
def processar_email(email: str) -> str:
    """Processa um email."""
    if "@" not in email:
        raise RetryAgentRun("Formato de email invalido. Use usuario@dominio.com")
    return f"Email {email} processado"


# Requisitos de Estado
@tool
def finalizar_pedido(run_context: RunContext) -> str:
    """Finaliza o pedido do carrinho."""
    state = ensure_state(run_context)
    carrinho = state.get("carrinho", [])
    if not carrinho:
        raise RetryAgentRun("Carrinho vazio. Adicione itens antes de finalizar.")
    return f"Pedido finalizado: {carrinho}"


# Logica de Negocio
@tool
def aprovar_desconto(percentual: int) -> str:
    """Aprova um desconto percentual."""
    if percentual > 20:
        raise RetryAgentRun(
            f"Desconto de {percentual}% excede o limite de 20%."
        )
    return f"Desconto de {percentual}% aprovado"
```

### StopAgentRun

Para o loop de tool calls imediatamente. A mensagem e usada como conteudo final da resposta.

```python
from app.runtime import tool, StopAgentRun


@tool
def verificar_limite(valor: int) -> str:
    """Verifica se um valor esta dentro do limite."""
    if valor > 100:
        raise StopAgentRun(
            f"Valor {valor} excede o limite. Execucao interrompida."
        )
    return f"Valor {valor} esta dentro do limite."
```

### Fluxo de Execucao no Agent Loop

```
┌──────────────────────────────────────────────────────────────────┐
│                        Agent Loop                                │
│                    (app/agent_loop.py)                            │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │litellm.acom- │───>│  ToolRegistry│───>│   Resultado  │       │
│  │  pletion()   │    │  .execute()  │    │   (string)   │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         │                   v                   │                │
│         │          ┌────────────────┐            │                │
│         │          │ RetryAgentRun  │────────────┘                │
│         │          │  (feedback p/  │     (resultado vai como    │
│         │          │   o LLM)      │      tool result, loop     │
│         │          └────────────────┘      continua)             │
│         │                   │                                    │
│         │                   v                                    │
│         │          ┌────────────────┐                            │
│         │          │ StopAgentRun   │───────> Loop FINALIZADO    │
│         │          │ (para o loop)  │                            │
│         │          └────────────────┘                            │
│         │                                                        │
│         │          ┌────────────────┐                            │
│         │          │ Truncamento    │   TOOL_OUTPUT_MAX_CHARS    │
│         │          │ da saida       │   (default: 500 chars)    │
│         │          └────────────────┘                            │
└──────────────────────────────────────────────────────────────────┘
```

### Quando Usar Cada Exception

| Cenario                    | Exception        | Exemplo                    |
|----------------------------|------------------|----------------------------|
| Validacao falhou           | `RetryAgentRun`  | Email invalido             |
| Pre-requisito nao atendido | `RetryAgentRun`  | Carrinho vazio             |
| Refinamento iterativo      | `RetryAgentRun`  | Precisa de mais dados      |
| Limite critico atingido    | `StopAgentRun`   | Valor excede threshold     |
| Condicao de parada         | `StopAgentRun`   | Objetivo alcancado         |
| Erro irrecuperavel         | `StopAgentRun`   | Permissao negada           |

---

## Boas Praticas para Tools

| Pratica                | Descricao                                                        |
|------------------------|------------------------------------------------------------------|
| **Docstring completa** | O LLM usa a primeira linha para decidir quando usar a tool       |
| **Type hints**         | Obrigatorios -- definem o JSON Schema de parametros              |
| **Retorne strings**    | O resultado e sempre convertido para `str` pelo `ToolRegistry`   |
| **Trate erros**        | Use `RetryAgentRun` para feedback, `StopAgentRun` para parar    |
| **Valide inputs**      | Sempre validar antes de processar                                |
| **Saida concisa**      | Lembre que a saida e truncada em 500 chars por padrao            |
| **Um arquivo por tool**| Mantenha cada tool em seu proprio arquivo em `app/tools/`        |
| **Sem efeitos colaterais no schema** | O parametro `run_context` e filtrado automaticamente |

---

## Resumo dos Imports

Todos os imports necessarios para criar tools vem de `app.runtime`:

```python
from app.runtime import tool              # Decorator que gera ToolDefinition
from app.runtime import RunContext        # Contexto da sessao (session_state, user_id, etc.)
from app.runtime import RetryAgentRun     # Feedback para o LLM tentar novamente
from app.runtime import StopAgentRun      # Para o agent loop imediatamente
```

Helpers opcionais:

```python
from app.tools._helpers import ensure_state   # Garante que session_state existe
```

---

## Referencias

- [`app/runtime.py`](../app/runtime.py) -- Decorator `@tool`, `ToolDefinition`, `ToolRegistry`, `RunContext`, exceptions
- [`app/agent.py`](../app/agent.py) -- `get_tools_registry()` e registro das tools
- [`app/agent_loop.py`](../app/agent_loop.py) -- Agent loop iterativo com `litellm.acompletion()`
- [`app/tools/__init__.py`](../app/tools/__init__.py) -- Re-exports de todas as tools
- [`app/config.py`](../app/config.py) -- `TOOL_OUTPUT_MAX_CHARS` e demais configuracoes
