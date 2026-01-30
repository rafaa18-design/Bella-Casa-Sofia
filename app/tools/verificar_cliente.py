"""Tool para verificar se o canal atual pertence a um paciente cadastrado.

⚠️ Dados mockados — apenas para desenvolvimento/testes.
Em produção, consulte o banco de dados ou CRM real usando o identificador
do canal (ex: número de telefone no WhatsApp).
"""

from agno.tools import tool
from agno.run import RunContext

from app.tools._mock_data import CLIENTES_POR_CANAL, PACIENTES


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
