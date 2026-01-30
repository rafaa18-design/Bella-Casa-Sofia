"""Tool: consultar_historico_paciente — Histórico clínico do paciente."""

from datetime import datetime, timedelta

from agno.exceptions import RetryAgentRun
from agno.tools import tool

from app.tools._mock_data import DENTISTAS, PACIENTES, SERVICOS


@tool
def consultar_historico_paciente(paciente_id: str) -> str:
    """Consulta o histórico de consultas e tratamentos de um paciente.

    Use esta ferramenta para ver o histórico clínico do paciente.
    Primeiro busque o paciente com buscar_paciente para obter o ID.

    Args:
        paciente_id: ID do paciente (ex: PAC001).

    Returns:
        Histórico completo de consultas do paciente.
    """
    if paciente_id not in PACIENTES:
        ids_validos = ", ".join(PACIENTES.keys())
        raise RetryAgentRun(
            f'Paciente "{paciente_id}" não encontrado. '
            f"IDs cadastrados: {ids_validos}. "
            "Use a ferramenta buscar_paciente para encontrar o ID pelo nome."
        )

    pac = PACIENTES[paciente_id]
    historico = pac["historico"]

    if not historico:
        return f"Paciente {pac['nome']} não possui consultas anteriores registradas."

    linhas = [f"Histórico de {pac['nome']} ({paciente_id}):\n"]
    for i, h in enumerate(historico, 1):
        servico_nome = SERVICOS.get(h["servico"], {}).get("nome", h["servico"])
        dentista_nome = DENTISTAS.get(h["dentista"], {}).get("nome", h["dentista"])
        data_fmt = datetime.strptime(h["data"], "%Y-%m-%d").strftime("%d/%m/%Y")
        linhas.append(
            f"{i}. {data_fmt} - {servico_nome}\n"
            f"   Dentista: {dentista_nome}\n"
            f"   Obs: {h['obs']}"
        )

    proxima = datetime.strptime(historico[-1]["data"], "%Y-%m-%d") + timedelta(days=180)
    linhas.append(f"\n📅 Próxima revisão recomendada: {proxima.strftime('%d/%m/%Y')}")

    return "\n".join(linhas)
