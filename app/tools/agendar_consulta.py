"""Tool: agendar_consulta — Agenda consulta odontológica."""

from datetime import datetime

from agno.exceptions import RetryAgentRun
from agno.run import RunContext
from agno.tools import tool

from app.tools._helpers import gerar_agenda_mock, gerar_id_consulta
from app.tools._mock_data import DENTISTAS, HORARIOS_BASE, SERVICOS


@tool
def agendar_consulta(
    run_context: RunContext,
    paciente_nome: str,
    data: str,
    horario: str,
    servico: str,
    dentista_id: str,
) -> str:
    """Agenda uma consulta odontológica para o paciente.

    Use esta ferramenta após confirmar disponibilidade e dados com o paciente.
    Salva o agendamento no estado da sessão.

    Args:
        paciente_nome: Nome completo do paciente.
        data: Data da consulta no formato YYYY-MM-DD.
        horario: Horário desejado (ex: 09:00, 14:30).
        servico: Código do serviço (ex: limpeza, canal, clareamento).
        dentista_id: ID do dentista (ex: DRA001, DR002).

    Returns:
        Confirmação do agendamento com detalhes.
    """
    # Validar serviço
    if servico not in SERVICOS:
        servicos_validos = ", ".join(SERVICOS.keys())
        raise RetryAgentRun(
            f'Serviço "{servico}" não encontrado. '
            f"Serviços disponíveis: {servicos_validos}"
        )

    # Validar dentista
    if dentista_id not in DENTISTAS:
        dentistas_validos = ", ".join(
            f"{did} ({d['nome']})" for did, d in DENTISTAS.items()
        )
        raise RetryAgentRun(
            f'Dentista "{dentista_id}" não encontrado. '
            f"Dentistas disponíveis: {dentistas_validos}"
        )

    # Validar data
    try:
        data_obj = datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        raise RetryAgentRun(
            f'Data "{data}" em formato inválido. Use YYYY-MM-DD.'
        )

    # Validar horário
    if horario not in HORARIOS_BASE:
        raise RetryAgentRun(
            f'Horário "{horario}" inválido. '
            "Use horários de 30 em 30 minutos entre 08:00 e 17:30 (ex: 09:00, 14:30)."
        )

    # Verificar se horário está disponível
    disponiveis = gerar_agenda_mock(data, dentista_id)
    if data_obj.weekday() == 5:
        disponiveis = [h for h in disponiveis if h < "12:00"]

    if horario not in disponiveis:
        raise RetryAgentRun(
            f"Horário {horario} não está disponível para {DENTISTAS[dentista_id]['nome']} "
            f"em {data_obj.strftime('%d/%m/%Y')}. "
            f"Horários livres: {', '.join(disponiveis[:5])}..."
        )

    # Criar agendamento
    consulta_id = gerar_id_consulta()
    servico_info = SERVICOS[servico]
    dentista_info = DENTISTAS[dentista_id]

    agendamento = {
        "id": consulta_id,
        "paciente": paciente_nome,
        "data": data,
        "horario": horario,
        "servico": servico,
        "servico_nome": servico_info["nome"],
        "preco": servico_info["preco"],
        "duracao_min": servico_info["duracao_min"],
        "dentista_id": dentista_id,
        "dentista_nome": dentista_info["nome"],
        "status": "confirmado",
        "criado_em": datetime.now().isoformat(),
    }

    # Salvar no session state
    if not run_context.session_state:
        run_context.session_state = {}
    if "agendamentos" not in run_context.session_state:
        run_context.session_state["agendamentos"] = []
    run_context.session_state["agendamentos"].append(agendamento)
    run_context.session_state["ultimo_agendamento"] = agendamento

    preco_str = f"R$ {servico_info['preco']:.2f}" if servico_info["preco"] > 0 else "Gratuito"

    return (
        f"✅ Consulta agendada com sucesso!\n\n"
        f"📋 Código: {consulta_id}\n"
        f"👤 Paciente: {paciente_nome}\n"
        f"📅 Data: {data_obj.strftime('%d/%m/%Y')} às {horario}\n"
        f"🦷 Serviço: {servico_info['nome']}\n"
        f"👨‍⚕️ Dentista: {dentista_info['nome']}\n"
        f"⏱️ Duração: {servico_info['duracao_min']} minutos\n"
        f"💰 Valor: {preco_str}\n\n"
        f"Lembre-se: Chegar 15 minutos antes para preenchimento de ficha."
    )
