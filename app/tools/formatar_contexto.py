"""Formata session_state para injeção no contexto do agente.

Esta função NÃO é uma tool — é usada por main.py para adicionar
informações persistidas ao prompt do agente, garantindo que ele
não esqueça dados importantes mesmo quando o histórico de mensagens rola.
"""


def formatar_contexto_state(session_state: dict) -> str:
    """Formata o session_state para injeção no contexto do agente.

    Args:
        session_state: O session_state carregado do Redis.

    Returns:
        String formatada para ser adicionada às instructions do agente.
        Retorna string vazia se não houver dados relevantes.
    """
    partes = []

    # Dados do cliente
    cliente = session_state.get("cliente", {})
    if cliente:
        dados = []
        for k, v in cliente.items():
            if k != "atualizado_em" and v:
                dados.append(f"{k}: {v}")
        if dados:
            partes.append("DADOS DO CLIENTE ATUAL: " + " | ".join(dados))

    # Preferências
    prefs = session_state.get("preferencias", {})
    if prefs:
        items = [f"{k}: {info['valor']}" for k, info in prefs.items()]
        partes.append("PREFERÊNCIAS DO CLIENTE: " + " | ".join(items))

    # Agendamentos ativos
    agendamentos = session_state.get("agendamentos", [])
    ativos = [a for a in agendamentos if a.get("status") != "cancelado"]
    if ativos:
        items = []
        for a in ativos:
            items.append(
                f"{a['id']} - {a['servico_nome']} em {a['data']} às {a['horario']} "
                f"com {a['dentista_nome']}"
            )
        partes.append("AGENDAMENTOS ATIVOS: " + " | ".join(items))

    if not partes:
        return ""

    return (
        "\n\n--- CONTEXTO DA SESSÃO (dados já coletados, NÃO pergunte novamente) ---\n"
        + "\n".join(partes)
        + "\n--- FIM DO CONTEXTO ---"
    )


def formatar_contexto_completo(
    session_state: dict, memory_context: str = ""
) -> str:
    """Combina memória consolidada + estado da sessão para injeção no prompt.

    Args:
        session_state: O session_state carregado do Redis.
        memory_context: Texto de memória consolidada (fatos de longo prazo).

    Returns:
        String formatada combinando memória e contexto da sessão.
    """
    parts = []

    if memory_context:
        parts.append(
            "\n\n--- MEMÓRIA DE LONGO PRAZO ---\n"
            + memory_context
            + "\n--- FIM DA MEMÓRIA ---"
        )

    state_context = formatar_contexto_state(session_state)
    if state_context:
        parts.append(state_context)

    return "".join(parts)
