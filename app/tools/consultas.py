"""Tools de agendamento: agendar, cancelar e verificar disponibilidade."""

from datetime import datetime

from app.runtime import RetryAgentRun, RunContext, tool

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
