"""Tools de pacientes: buscar, histórico, verificar cliente e convênios."""

from datetime import datetime, timedelta

from app.runtime import RetryAgentRun, RunContext, tool

from app.tools._mock_data import (
    CLIENTES_POR_CANAL,
    CONVENIOS,
    DENTISTAS,
    PACIENTES,
    SERVICOS,
)


@tool
def buscar_paciente(nome: str) -> str:
    """Busca um paciente pelo nome no cadastro da clínica.

    Use esta ferramenta para encontrar dados cadastrais do paciente.

    Args:
        nome: Nome ou parte do nome do paciente.

    Returns:
        Dados cadastrais do paciente encontrado.
    """
    nome_lower = nome.lower()
    encontrados = []

    for pid, pac in PACIENTES.items():
        if nome_lower in pac["nome"].lower():
            convenio = pac["convenio"] or "Particular"
            encontrados.append(
                f"👤 {pac['nome']} (ID: {pid})\n"
                f"   📞 {pac['telefone']} | ✉️ {pac['email']}\n"
                f"   🎂 Nascimento: {pac['data_nascimento']}\n"
                f"   🏥 Convênio: {convenio}\n"
                f"   📊 Total de consultas: {len(pac['historico'])}"
            )

    if not encontrados:
        raise RetryAgentRun(
            f'Nenhum paciente encontrado com o nome "{nome}". '
            "Verifique a grafia ou peça o nome completo ao paciente."
        )

    return f"Pacientes encontrados ({len(encontrados)}):\n\n" + "\n\n".join(encontrados)


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


@tool
def verificar_cliente(run_context: RunContext) -> str:
    """Verifica se o canal da conversa atual pertence a um paciente já cadastrado.

    Use esta ferramenta NO INÍCIO de cada conversa para saber se quem está
    falando já é paciente da clínica. Não precisa de parâmetros — a identificação
    é feita automaticamente pelo canal (conversation_id).

    Returns:
        Dados do paciente se encontrado, ou aviso de paciente novo.
    """
    canal_id = run_context.session_id or ""

    # Busca pelo conversation_id (que em produção é o telefone/canal)
    paciente_id = CLIENTES_POR_CANAL.get(canal_id)

    if not paciente_id:
        return (
            "PACIENTE NOVO — este canal não tem cadastro na clínica. "
            "Trate como primeiro atendimento. "
            "Informe que a avaliação inicial é gratuita e colete os dados para cadastro."
        )

    pac = PACIENTES[paciente_id]
    convenio = pac["convenio"] or "Particular"
    ultima = pac["historico"][-1] if pac["historico"] else None
    ultima_info = (
        f"Última consulta: {ultima['data']} — {ultima['servico']}"
        if ultima
        else "Sem consultas anteriores"
    )

    return (
        f"PACIENTE CADASTRADO (ID: {paciente_id})\n"
        f"Nome: {pac['nome']}\n"
        f"CPF: {pac['cpf']}\n"
        f"Telefone: {pac['telefone']}\n"
        f"E-mail: {pac['email']}\n"
        f"Nascimento: {pac['data_nascimento']}\n"
        f"Convênio: {convenio}\n"
        f"Total de consultas: {len(pac['historico'])}\n"
        f"{ultima_info}"
    )


@tool
def consultar_convenios() -> str:
    """Lista todos os convênios aceitos pela clínica com detalhes de cobertura.

    Use esta ferramenta quando o paciente perguntar sobre convênios,
    planos odontológicos ou cobertura.

    Returns:
        Lista de convênios com coberturas e carências.
    """
    linhas = ["Convênios aceitos pela Clínica Sorriso:\n"]

    for nome, conv in CONVENIOS.items():
        linhas.append(f"🏥 {conv['nome']}")
        linhas.append(f"   Carência: {conv['carencia_dias']} dias")
        linhas.append("   Cobertura:")
        for servico_key, percentual in conv["cobertura"].items():
            servico_nome = SERVICOS.get(servico_key, {}).get("nome", servico_key)
            linhas.append(f"     • {servico_nome}: {int(percentual * 100)}%")
        linhas.append(f"   ⚠️ {conv['observacao']}")
        linhas.append("")

    linhas.append("💡 Pacientes particulares têm 10% de desconto à vista.")
    return "\n".join(linhas)
