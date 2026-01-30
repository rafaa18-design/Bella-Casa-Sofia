"""Tool: salvar_preferencias — Persiste preferências do paciente na sessão."""

from datetime import datetime

from agno.run import RunContext
from agno.tools import tool

from app.tools._helpers import ensure_state


@tool
def salvar_preferencias(
    run_context: RunContext,
    chave: str,
    valor: str,
) -> str:
    """Salva uma preferência ou anotação temporária do paciente para esta sessão.

    Use esta ferramenta para guardar qualquer informação relevante que o paciente
    mencione e que pode ser útil durante o atendimento, como:
    - Horários preferidos (ex: "prefere manhã", "só pode terça e quinta")
    - Dentista preferido (ex: "prefere Dra. Maria")
    - Alergias ou observações (ex: "alergia a látex", "ansioso com agulhas")
    - Procedimentos de interesse (ex: "interessado em clareamento")
    - Qualquer outra nota relevante

    Args:
        chave: Nome da preferência (ex: "horario_preferido", "dentista_preferido", "alergias").
        valor: Valor da preferência (ex: "manhã, terça ou quinta", "Dra. Maria Silva").

    Returns:
        Confirmação da preferência salva.
    """
    state = ensure_state(run_context)

    if "preferencias" not in state:
        state["preferencias"] = {}

    state["preferencias"][chave] = {
        "valor": valor,
        "salvo_em": datetime.now().isoformat(),
    }

    return f"Preferência salva: {chave} = {valor}"
