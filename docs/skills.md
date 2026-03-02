# Skills (Habilidades)

Skills sao pacotes auto-contidos de capacidades que um agente pode usar para estender sua atuacao em dominios especificos. Uma skill agrupa instrucoes, tools e referencias relacionadas a uma competencia.

---

## Abordagem

Skills sao implementadas como **conjuntos especializados de tools** registrados condicionalmente no `get_tools_registry()` de `app/agent.py`.

---

## Como Implementar

### 1. Skill como Conjunto de Tools

Cada skill e um modulo Python que exporta uma lista de tools relacionadas:

```python
# app/tools/skills/code_review.py

"""Skill: code-review -- Revisao de codigo com boas praticas."""

from app.runtime import tool


@tool
def analisar_estrutura(codigo: str) -> str:
    """Analisa a estrutura e organizacao do codigo."""
    # Logica de analise
    return f"Analise estrutural de {len(codigo)} caracteres concluida."


@tool
def verificar_estilo(codigo: str) -> str:
    """Verifica conformidade com guia de estilo."""
    issues = []
    for i, line in enumerate(codigo.split('\n'), 1):
        if len(line) > 100:
            issues.append(f"Linha {i}: excede 100 caracteres")
    return f"Encontrados {len(issues)} problemas de estilo."


# Exportar todas as tools da skill
SKILL_TOOLS = [analisar_estrutura, verificar_estilo]
```

### 2. Registro Condicional no Registry

Registre skills condicionalmente baseado em configuracao ou contexto:

```python
# app/agent.py

from app.runtime import ToolRegistry
from app.tools import (
    listar_servicos,
    verificar_disponibilidade,
    # ... tools base
)


def get_tools_registry(skills: list[str] | None = None) -> ToolRegistry:
    """Registra tools no ToolRegistry, incluindo skills opcionais."""
    registry = ToolRegistry()

    # Tools base (sempre disponiveis)
    base_tools = [
        listar_servicos,
        verificar_disponibilidade,
        # ...
    ]
    for t in base_tools:
        registry.register(t)

    # Skills opcionais
    if skills and "code_review" in skills:
        from app.tools.skills.code_review import SKILL_TOOLS
        for t in SKILL_TOOLS:
            registry.register(t)

    if skills and "data_analysis" in skills:
        from app.tools.skills.data_analysis import SKILL_TOOLS
        for t in SKILL_TOOLS:
            registry.register(t)

    return registry
```

### 3. Instrucoes da Skill no System Prompt

Adicione instrucoes especificas da skill ao system prompt em `build_system_messages()`:

```python
# app/agent.py

SKILL_INSTRUCTIONS = {
    "code_review": (
        "Voce tem acesso a ferramentas de revisao de codigo. "
        "Ao revisar codigo, analise estrutura primeiro, depois estilo."
    ),
    "data_analysis": (
        "Voce tem acesso a ferramentas de analise de dados. "
        "Sempre apresente resultados com tabelas quando possivel."
    ),
}


def build_system_messages(
    instructions: str,
    text_message: str,
    images: list[dict] | None = None,
    history: list[dict] | None = None,
    active_skills: list[str] | None = None,
) -> list[dict]:
    """Build messages com instrucoes de skills injetadas."""

    # Injetar instrucoes de skills ativas
    if active_skills:
        skill_text = "\n".join(
            SKILL_INSTRUCTIONS[s] for s in active_skills
            if s in SKILL_INSTRUCTIONS
        )
        instructions = f"{instructions}\n\n## Skills Ativas\n{skill_text}"

    messages = [{"role": "system", "content": instructions}]
    # ... resto da construcao de mensagens
    return messages
```

### 4. Estrutura de Diretorio Sugerida

```
app/tools/
├── __init__.py              # Tools base + exports
├── _helpers.py
├── _mock_data.py
├── obter_data_hora.py
├── salvar_dados_cliente.py
└── skills/                  # Skills opcionais
    ├── __init__.py
    ├── code_review.py       # Skill: revisao de codigo
    └── data_analysis.py     # Skill: analise de dados
```

---

## Resumo

| Componente | Descricao |
|------------|-----------|
| Modulos de skill | Modulos Python com `SKILL_TOOLS` list |
| Instrucoes de skill | Dicionario `SKILL_INSTRUCTIONS` injetado no system prompt |
| Registro condicional | `get_tools_registry(skills=[...])` registra tools conforme necessidade |
| Tools da skill | Tools com `@tool` decorator em `app/runtime` |
