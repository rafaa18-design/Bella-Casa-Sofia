"""Tool: verificar_disponibilidade — Verifica horários disponíveis."""

from datetime import datetime

from agno.exceptions import RetryAgentRun
from agno.tools import tool

from app.tools._helpers import gerar_agenda_mock
from app.tools._mock_data import DENTISTAS


@tool
def verificar_disponibilidade(data: str, dentista: str = "") -> str:
    """Verifica horários disponíveis para uma data e dentista específicos.

    Use esta ferramenta para consultar a agenda antes de agendar uma consulta.

    Args:
        data: Data desejada no formato YYYY-MM-DD (ex: 2025-02-15).
        dentista: ID ou nome do dentista (ex: DRA001, "Maria"). Se vazio, mostra todos.

    Returns:
        Lista de horários disponíveis para a data e dentista.
    """
    # Validar formato da data
    try:
        data_obj = datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        raise RetryAgentRun(
            f'Data "{data}" em formato inválido. Use o formato YYYY-MM-DD (ex: 2025-02-15).'
        )

    # Não permitir datas passadas
    if data_obj.date() < datetime.now().date():
        raise RetryAgentRun(
            "Não é possível agendar em datas passadas. "
            "Por favor, escolha uma data futura."
        )

    # Não permitir domingos
    if data_obj.weekday() == 6:
        raise RetryAgentRun(
            "A clínica não funciona aos domingos. "
            "Por favor, escolha outra data (segunda a sábado)."
        )

    # Buscar dentista
    dentistas_encontrados = {}
    if dentista:
        dentista_lower = dentista.lower()
        for did, info in DENTISTAS.items():
            if did.lower() == dentista_lower or dentista_lower in info["nome"].lower():
                dentistas_encontrados[did] = info
        if not dentistas_encontrados:
            nomes = ", ".join(f"{d['nome']} ({did})" for did, d in DENTISTAS.items())
            raise RetryAgentRun(
                f'Dentista "{dentista}" não encontrado. Dentistas disponíveis: {nomes}'
            )
    else:
        dentistas_encontrados = DENTISTAS

    # Sábado: horário reduzido (8h-12h)
    is_sabado = data_obj.weekday() == 5

    linhas = [f"Horários disponíveis para {data_obj.strftime('%d/%m/%Y')}"]
    if is_sabado:
        linhas.append("(Sábado - horário reduzido: 08:00 às 12:00)\n")
    else:
        linhas.append("")

    for did, info in dentistas_encontrados.items():
        horarios = gerar_agenda_mock(data, did)
        if is_sabado:
            horarios = [h for h in horarios if h < "12:00"]
        linhas.append(f"🦷 {info['nome']} ({info['especialidade']}):")
        if horarios:
            linhas.append(f"   {', '.join(horarios)}")
        else:
            linhas.append("   Sem horários disponíveis nesta data.")

    return "\n".join(linhas)
