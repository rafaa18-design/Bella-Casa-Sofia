"""Tools de sessão: salvar dados do cliente, preferências e ver contexto."""

from datetime import datetime

from app.runtime import RunContext, tool

from app.tools._helpers import ensure_state


@tool
def salvar_dados_cliente(
    run_context: RunContext,
    nome: str,
    paciente_id: str = "",
    telefone: str = "",
    email: str = "",
    convenio: str = "",
    cpf: str = "",
) -> str:
    """Salva ou atualiza os dados cadastrais do cliente da sessão atual.

    IMPORTANTE: Use esta ferramenta SEMPRE que o paciente informar dados pessoais
    como nome, telefone, e-mail, convênio ou CPF. Isso garante que os dados persistam
    durante toda a conversa, mesmo em interações longas.

    Apenas preencha os campos que o paciente informou. Campos vazios não sobrescrevem
    dados já salvos.

    Args:
        nome: Nome completo do paciente.
        paciente_id: ID do paciente no sistema (ex: PAC001), se já localizado.
        telefone: Telefone com DDD.
        email: E-mail do paciente.
        convenio: Nome do convênio (ex: OdontoPrev, Bradesco Dental).
        cpf: CPF do paciente.

    Returns:
        Confirmação dos dados salvos.
    """
    state = ensure_state(run_context)

    if "cliente" not in state:
        state["cliente"] = {}

    cliente = state["cliente"]

    # Só atualiza campos que foram informados (não-vazios)
    if nome:
        cliente["nome"] = nome
    if paciente_id:
        cliente["paciente_id"] = paciente_id
    if telefone:
        cliente["telefone"] = telefone
    if email:
        cliente["email"] = email
    if convenio:
        cliente["convenio"] = convenio
    if cpf:
        cliente["cpf"] = cpf

    cliente["atualizado_em"] = datetime.now().isoformat()

    partes = ["Dados do cliente salvos:"]
    for k, v in cliente.items():
        if k != "atualizado_em" and v:
            partes.append(f"  • {k}: {v}")

    return "\n".join(partes)


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


@tool
def ver_contexto_sessao(run_context: RunContext) -> str:
    """Recupera todos os dados do cliente e preferências salvos nesta sessão.

    Use esta ferramenta no início de um atendimento ou quando precisar relembrar
    informações do paciente que foram coletadas anteriormente na conversa.
    Isso é especialmente útil em conversas longas.

    Returns:
        Resumo de todos os dados e preferências salvos na sessão.
    """
    state = ensure_state(run_context)

    linhas = []

    # Dados do cliente
    cliente = state.get("cliente", {})
    if cliente:
        linhas.append("📋 Dados do cliente:")
        for k, v in cliente.items():
            if k != "atualizado_em" and v:
                linhas.append(f"  • {k}: {v}")
    else:
        linhas.append("📋 Nenhum dado do cliente salvo ainda.")

    # Preferências
    prefs = state.get("preferencias", {})
    if prefs:
        linhas.append("\n⭐ Preferências:")
        for k, info in prefs.items():
            linhas.append(f"  • {k}: {info['valor']}")
    else:
        linhas.append("\n⭐ Nenhuma preferência registrada.")

    # Agendamentos
    agendamentos = state.get("agendamentos", [])
    ativos = [a for a in agendamentos if a.get("status") != "cancelado"]
    if ativos:
        linhas.append(f"\n📅 Agendamentos ativos ({len(ativos)}):")
        for a in ativos:
            linhas.append(
                f"  • {a['id']}: {a['servico_nome']} em {a['data']} às {a['horario']} "
                f"com {a['dentista_nome']}"
            )

    return "\n".join(linhas) if linhas else "Sessão vazia — nenhum dado salvo ainda."
