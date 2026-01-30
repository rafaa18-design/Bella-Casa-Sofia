"""Tool: ver_contexto_sessao — Recupera dados salvos na sessão."""

from agno.run import RunContext
from agno.tools import tool

from app.tools._helpers import ensure_state


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
