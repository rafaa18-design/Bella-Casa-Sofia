"""Tool: consultar_convenios — Lista convênios aceitos."""

from agno.tools import tool

from app.tools._mock_data import CONVENIOS, SERVICOS


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
