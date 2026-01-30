"""Tool: buscar_paciente — Busca paciente por nome."""

from agno.exceptions import RetryAgentRun
from agno.tools import tool

from app.tools._mock_data import PACIENTES


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
