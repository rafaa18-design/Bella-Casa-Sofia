"""Tool: salvar_dados_cliente — Persiste dados cadastrais do cliente na sessão."""

from datetime import datetime

from agno.run import RunContext
from agno.tools import tool

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
