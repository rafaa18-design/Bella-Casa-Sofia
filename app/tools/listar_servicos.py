"""Tool: listar_servicos — Lista serviços odontológicos disponíveis."""

from agno.tools import tool

from app.tools._mock_data import SERVICOS


@tool
def listar_servicos() -> str:
    """Lista todos os serviços odontológicos disponíveis na clínica com preços e duração.

    Use esta ferramenta quando o paciente perguntar sobre serviços, procedimentos,
    preços ou o que a clínica oferece.

    Returns:
        Lista formatada de todos os serviços com preço e duração.
    """
    linhas = ["Serviços disponíveis na Clínica Sorriso:\n"]
    for key, s in SERVICOS.items():
        preco = f"R$ {s['preco']:.2f}" if s["preco"] > 0 else "Gratuito"
        linhas.append(
            f"• {s['nome']} ({key}): {preco} | {s['duracao_min']} min\n"
            f"  {s['descricao']}"
        )
    return "\n".join(linhas)
