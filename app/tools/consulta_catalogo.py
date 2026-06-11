"""Tool de consulta ao catálogo de produtos da Bella Casa (móveis Corbelli).

A base é gerada por scripts/build_catalogo.py a partir da Tabela de Fidelidade,
e fica em catalogo/produtos.json. Os produtos são agrupados por nome para
apresentar ao cliente um item por modelo (com faixa de preço e variações).
"""

import json
import logging
import os
import re
import unicodedata

from app.runtime import RunContext, tool

logger = logging.getLogger(__name__)

_CATALOGO_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "catalogo", "produtos.json"
)

# Mapeia termos do cliente -> categoria do catálogo
_CAT_ALIASES = {
    "sofa": "SOFÁ", "sofá": "SOFÁ", "sofas": "SOFÁ", "sofás": "SOFÁ",
    "modulo": "MÓDULO", "módulo": "MÓDULO", "modulos": "MÓDULO",
    "mesa": "MESA", "mesas": "MESA",
    "cadeira": "CADEIRA", "cadeiras": "CADEIRA",
    "poltrona": "POLTRONA", "poltronas": "POLTRONA",
    "aparador": "APARADOR", "aparadores": "APARADOR",
    "banqueta": "BANQUETA", "banquetas": "BANQUETA",
    "estante": "ESTANTE", "estantes": "ESTANTE",
    "puff": "PUFF", "puffs": "PUFF",
    "chaise": "CHAISE",
    "buffet": "BUFFET", "rack": "RACK", "espelho": "ESPELHO",
}


def _strip(s: str) -> str:
    """Minúsculas e sem acento, para comparação tolerante."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _load_catalogo() -> list[dict]:
    try:
        with open(_CATALOGO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Falha ao carregar catálogo: {e}")
        return []


# Carrega uma vez no import (cache em memória)
_PRODUTOS = _load_catalogo()
logger.info(f"Catálogo carregado: {len(_PRODUTOS)} variantes de produto")


def _money(v) -> str:
    try:
        return "R$ " + f"{int(round(float(v))):,}".replace(",", ".")
    except (ValueError, TypeError):
        return ""


def _medida_str(m: dict) -> str:
    c, a, p = m.get("C"), m.get("A"), m.get("P")
    if not (c and a and p):
        return ""
    fmt = lambda x: f"{x:.2f}".replace(".", ",")  # noqa: E731
    return f"{fmt(c)} x {fmt(a)} x {fmt(p)} m (C x A x P)"


def _agrupar(variantes: list[dict]) -> dict:
    """Agrupa variantes do mesmo nome num único produto para o cliente."""
    nome = variantes[0]["nome"]
    categoria = variantes[0]["categoria"]
    precos_min = [v["preco_min"] for v in variantes if v.get("preco_min")]
    precos_max = [v["preco_max"] for v in variantes if v.get("preco_max")]
    pmin, pmax = min(precos_min), max(precos_max)
    por_tecido = any(v.get("tipo_preco") == "faixa" for v in variantes)

    if por_tecido:
        preco_texto = f"de {_money(pmin)} a {_money(pmax)} (varia conforme o tecido)"
    elif pmin == pmax:
        preco_texto = _money(pmin)
    else:
        preco_texto = f"de {_money(pmin)} a {_money(pmax)}"

    # Tamanhos e materiais distintos (até 3 de cada)
    tamanhos, materiais = [], []
    for v in variantes:
        ms = _medida_str(v.get("medidas_m", {}))
        if ms and ms not in tamanhos:
            tamanhos.append(ms)
        mat = re.sub(r"\s+\.", ".", (v.get("material") or "").strip())
        if mat and mat not in materiais:
            materiais.append(mat)

    return {
        "nome": nome,
        "categoria": categoria,
        "preco": preco_texto,
        "tamanhos": tamanhos[:3],
        "materiais": materiais[:3],
        "variacoes": len(variantes),
    }


@tool
def consultar_catalogo(run_context: RunContext, categoria: str = "", busca: str = "") -> str:
    """Consulta o catálogo de móveis da Bella Casa (linha Corbelli).

    Use SOMENTE quando o cliente pedir sugestão de produto ou perguntar sobre
    um móvel específico (modelo, medidas, material ou preço). NUNCA invente
    produtos, medidas ou preços — baseie-se EXCLUSIVAMENTE no que esta tool retornar.

    Parâmetros (pelo menos um deve ser informado):
    - categoria: tipo de móvel (sofá, mesa, cadeira, poltrona, aparador, banqueta,
      estante, puff, chaise, módulo). Opcional.
    - busca: palavra-chave para o nome ou material (ex: "ABBA", "teca", "alumínio",
      "pedra"). Opcional.

    Retorna até 5 produtos agrupados por modelo, cada um com: nome, medidas
    disponíveis, materiais e preço. O preço pode ser único (móveis rígidos) ou
    faixa "de X a Y conforme o tecido" (estofados). Se nada for encontrado,
    retorna lista vazia — nesse caso, ofereça encaminhar para a vendedora.
    """
    if not _PRODUTOS:
        return '{"resultados": [], "total_encontrado": 0, "erro": "catálogo indisponível"}'

    cat_alvo = _CAT_ALIASES.get(_strip(categoria)) if categoria else None
    termos = [t for t in _strip(busca).split() if len(t) > 2]

    # Categoria não reconhecida (ex: "geladeira") vira termo de busca
    if categoria and not cat_alvo:
        termos += [t for t in _strip(categoria).split() if len(t) > 2]

    # Exige ao menos um filtro real — sem isso, não despeja o catálogo inteiro
    if not cat_alvo and not termos:
        return '{"resultados": [], "total_encontrado": 0}'

    # Filtra por categoria e/ou termos de busca, com pontuação
    candidatos = []
    for p in _PRODUTOS:
        if cat_alvo and p["categoria"] != cat_alvo:
            continue
        alvo_nome = _strip(p["nome"])
        alvo_mat = _strip(p.get("material", ""))
        score = 0
        if termos:
            for t in termos:
                if t in alvo_nome:
                    score += 3
                elif t in alvo_mat:
                    score += 1
            if score == 0:
                continue
        candidatos.append((score, p))

    if not candidatos:
        return '{"resultados": [], "total_encontrado": 0}'

    # Agrupa por nome, somando o melhor score do grupo
    grupos: dict[str, list] = {}
    score_grupo: dict[str, int] = {}
    for score, p in candidatos:
        grupos.setdefault(p["nome"], []).append(p)
        score_grupo[p["nome"]] = max(score_grupo.get(p["nome"], 0), score)

    ordenados = sorted(grupos.items(), key=lambda kv: -score_grupo[kv[0]])
    resultados = [_agrupar(v) for _, v in ordenados[:5]]

    out = {"resultados": resultados, "total_encontrado": len(grupos)}
    return json.dumps(out, ensure_ascii=False)
