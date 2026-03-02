"""Funções auxiliares compartilhadas entre as tools."""

import random
import string

from app.runtime import RunContext

from app.tools._mock_data import HORARIOS_BASE


def ensure_state(run_context: RunContext) -> dict:
    """Garante que o session_state existe e retorna."""
    if not run_context.session_state:
        run_context.session_state = {}
    return run_context.session_state


def gerar_agenda_mock(data: str, dentista_id: str) -> list[str]:
    """Gera agenda mockada com alguns horários já ocupados."""
    random.seed(hash(f"{data}-{dentista_id}"))
    todos = list(HORARIOS_BASE)
    # Remove 4-8 horários aleatórios (já agendados)
    ocupados = random.sample(todos, min(random.randint(4, 8), len(todos)))
    return sorted(set(todos) - set(ocupados))


def gerar_id_consulta() -> str:
    """Gera ID único para consulta."""
    chars = string.ascii_uppercase + string.digits
    return "CON-" + "".join(random.choices(chars, k=6))
