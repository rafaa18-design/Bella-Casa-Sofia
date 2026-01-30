"""Tool: cancelar_consulta — Cancela consulta agendada."""

from datetime import datetime

from agno.exceptions import RetryAgentRun
from agno.run import RunContext
from agno.tools import tool


@tool
def cancelar_consulta(run_context: RunContext, consulta_id: str) -> str:
    """Cancela uma consulta agendada pelo código de identificação.

    Use esta ferramenta quando o paciente deseja cancelar uma consulta.
    A consulta deve ter sido agendada na sessão atual.

    Args:
        consulta_id: Código da consulta (ex: CON-ABC123).

    Returns:
        Confirmação do cancelamento.
    """
    if not run_context.session_state or "agendamentos" not in run_context.session_state:
        raise RetryAgentRun(
            "Nenhuma consulta encontrada na sessão atual. "
            "Verifique o código da consulta ou peça para o paciente informar os dados."
        )

    agendamentos = run_context.session_state["agendamentos"]
    for i, ag in enumerate(agendamentos):
        if ag["id"] == consulta_id:
            if ag["status"] == "cancelado":
                raise RetryAgentRun(
                    f"A consulta {consulta_id} já foi cancelada anteriormente."
                )
            ag["status"] = "cancelado"
            ag["cancelado_em"] = datetime.now().isoformat()
            return (
                f"❌ Consulta cancelada com sucesso.\n\n"
                f"📋 Código: {consulta_id}\n"
                f"👤 Paciente: {ag['paciente']}\n"
                f"📅 Data: {ag['data']} às {ag['horario']}\n"
                f"🦷 Serviço: {ag['servico_nome']}\n\n"
                f"O horário foi liberado na agenda."
            )

    ids_disponiveis = [ag["id"] for ag in agendamentos if ag["status"] != "cancelado"]
    raise RetryAgentRun(
        f'Consulta "{consulta_id}" não encontrada. '
        f"Consultas ativas: {', '.join(ids_disponiveis) if ids_disponiveis else 'nenhuma'}"
    )
