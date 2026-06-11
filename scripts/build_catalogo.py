"""Extrai a Tabela de Fidelidade Corbelli (PDF) para uma base estruturada JSON.

Cada linha de produto vira um registro com:
  categoria, nome, variante, material, tipo (INT/EXT), codigo,
  medidas {C, A, P}, peso_bruto, peso_liquido, m3, preco

Uso:
  python scripts/build_catalogo.py
Saída:
  catalogo/produtos.json
"""

import glob
import json
import os
import re

import pdfplumber

BASE = os.path.join(os.path.dirname(__file__), "..", "catalogo")
TAB = glob.glob(os.path.join(BASE, "*[Ff][Ii][Dd]*.pdf"))[0]
OUT = os.path.join(BASE, "produtos.json")

# Posições X (pt) das colunas de ESPECIFICAÇÃO (lado esquerdo da tabela)
SPEC_COLS = {"C": 223, "A": 253, "P": 283, "bruto": 298, "liquido": 320, "m3": 352}
# Tokens numéricos à direita deste X são PREÇOS (1 = preço único; vários = grupos de tecido)
PRECO_X_MIN = 372

# Palavras-chave que iniciam um novo "card" de produto
CATEGORIAS = (
    "APARADOR", "POLTRONA", "MESA", "BANCO", "BUFFET", "BAR", "ESPELHO",
    "CADEIRA", "SOFÁ", "SOFA", "PUFF", "CONJUNTO", "RACK", "BANQUETA",
    "CRISTALEIRA", "ESTANTE", "BALCÃO", "BAÚ", "MÓDULO", "MODULO",
    "CHAISE", "NAMORADEIRA", "DIVÃ", "RECAMIER", "TRIANGULAR", "CARRO", "BASE",
)

# Normalização de acentos/variações de categoria
CAT_NORM = {"SOFA": "SOFÁ", "MODULO": "MÓDULO", "DIVA": "DIVÃ"}

HEADER_WORDS = ("MEDIDAS", "PESOS", "BRUTO", "LÍQUIDO", "LIQUIDO", "PREÇO", "PRECO", "M3", "ÍNDICE", "INDEX")

NUM = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2,3}$|^\d+,\d{2,3}$")


def merge_numeric(words):
    """Funde fragmentos numéricos adjacentes (ex: '1' + ',10' -> '1,10')."""
    ws = sorted(words, key=lambda w: w["x0"])
    merged, cur = [], None
    for w in ws:
        is_frag = re.match(r"^[\d.,]+$", w["text"])
        if cur and is_frag and re.match(r"^[\d.,]+$", cur["text"]) and (w["x0"] - cur["x1"] < 4):
            cur = {"text": cur["text"] + w["text"], "x0": cur["x0"], "x1": w["x1"]}
        else:
            if cur:
                merged.append(cur)
            cur = {"text": w["text"], "x0": w["x0"], "x1": w["x1"]}
    if cur:
        merged.append(cur)
    return merged


def cluster_rows(words):
    rows = {}
    for w in words:
        rows.setdefault(round(w["top"] / 3) * 3, []).append(w)
    return [(y, rows[y]) for y in sorted(rows)]


def assign_specs_and_prices(merged_tokens):
    """Separa specs (x < PRECO_X_MIN, ancorados por coluna) de preços (x >= PRECO_X_MIN)."""
    specs = {}
    precos = []
    for t in merged_tokens:
        if not NUM.match(t["text"]):
            continue
        if t["x0"] >= PRECO_X_MIN:
            precos.append((t["x0"], br_to_float(t["text"])))
        elif t["x0"] > 205:
            col = min(SPEC_COLS, key=lambda c: abs(SPEC_COLS[c] - t["x0"]))
            if col not in specs or abs(SPEC_COLS[col] - t["x0"]) < abs(SPEC_COLS[col] - specs[col][1]):
                specs[col] = (t["text"], t["x0"])
    specs = {k: v[0] for k, v in specs.items()}
    precos = [p for _, p in sorted(precos) if p and p > 50]
    return specs, precos


def br_to_float(s):
    if not s:
        return None
    return float(s.replace(".", "").replace(",", "."))


def is_spaced(s):
    """Detecta material com letras separadas (ex: 's t r u t u r a')."""
    toks = s.split()
    if len(toks) < 4:
        return False
    return sum(1 for t in toks if len(t) == 1) / len(toks) > 0.4


def parse_page(page):
    words = page.extract_words(x_tolerance=1.5)
    rows = cluster_rows(words)

    # Chars brutos por linha — preservam os espaços reais do PDF
    char_rows = {}
    for c in page.chars:
        char_rows.setdefault(round(c["top"] / 3) * 3, []).append(c)

    def char_material(y):
        cs = sorted([c for c in char_rows.get(y, []) if 148 < c["x0"] < 470],
                    key=lambda c: c["x0"])
        raw = "".join(c["text"] for c in cs).strip()
        raw = re.sub(r"\s{2,}", " ", raw)
        # Colapsa runs de letra única ('a v u l s a' -> 'avulsa')
        if is_spaced(raw):
            raw = re.sub(r"\b(\w(?: \w){2,})\b",
                         lambda m: m.group(0).replace(" ", ""), raw)
        return raw.strip()

    produtos = []
    base_nome = ""
    variante = ""
    material = ""
    for y, toks in rows:
        # Texto: palavras cruas com espaço
        name_band = [t["text"] for t in toks
                     if 110 < t["x0"] < 205 and t["text"].isupper() and len(t["text"]) > 1
                     and not any(h in t["text"] for h in HEADER_WORDS)]
        mat_band = [t["text"] for t in toks
                    if t["x0"] > 198 and re.search(r"[a-zà-ú]", t["text"])
                    and not t["text"].startswith(("TECIDO", "Assento", "Encosto", "Almofada"))]

        joined_name = " ".join(name_band)
        if name_band:
            if any(c in joined_name for c in CATEGORIAS):
                base_nome = joined_name
                variante = ""
            else:
                variante = joined_name
        if mat_band:
            mw = " ".join(mat_band)
            # Se as palavras saíram com letras espaçadas, reconstrói pelos chars brutos
            material = char_material(y) if is_spaced(mw) else mw
            # Remove prefixo do nome que vaza em linhas compartilhadas (ex: 'SOFÁ ABBA avulsa')
            if base_nome and material.upper().startswith(base_nome.upper()):
                material = material[len(base_nome):].strip()

        # Números: specs (esquerda) e preços (direita)
        specs, precos = assign_specs_and_prices(merge_numeric(toks))

        if precos and "C" in specs:
            cat = base_nome.split()[0] if base_nome else ""
            cat = CAT_NORM.get(cat, cat)
            faixa = len(precos) > 1
            produtos.append({
                "categoria": cat,
                "nome": base_nome,
                "variante": variante,
                "material": material,
                "medidas_m": {"C": br_to_float(specs.get("C")),
                              "A": br_to_float(specs.get("A")),
                              "P": br_to_float(specs.get("P"))},
                "peso_bruto": br_to_float(specs.get("bruto")),
                "peso_liquido": br_to_float(specs.get("liquido")),
                "m3": br_to_float(specs.get("m3")),
                "tipo_preco": "faixa" if faixa else "unico",
                "preco_min": min(precos),
                "preco_max": max(precos),
                "precos_grupos": precos if faixa else None,
            })
    return produtos


def main():
    todos = []
    with pdfplumber.open(TAB) as pdf:
        for page in pdf.pages:
            try:
                todos.extend(parse_page(page))
            except Exception as e:  # noqa: BLE001
                print(f"  [aviso] pág {page.page_number}: {e}")

    # Filtra registros sem nome ou preço plausível
    limpos = [p for p in todos if p["nome"] and p["preco_min"] and p["preco_min"] > 50]

    # Segurança: material ainda quebrado vira vazio (nunca enviar texto truncado ao cliente)
    garbled = 0
    for p in limpos:
        if is_spaced(p["material"]):
            p["material"] = ""
            garbled += 1

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(limpos, f, ensure_ascii=False, indent=2)

    cats = {}
    faixa = sum(1 for p in limpos if p["tipo_preco"] == "faixa")
    for p in limpos:
        cats[p["categoria"]] = cats.get(p["categoria"], 0) + 1
    sem_mat = sum(1 for p in limpos if not p["material"])
    print(f"Total de registros extraídos: {len(todos)}")
    print(f"Registros válidos salvos:     {len(limpos)}")
    print(f"  - preço único (rígidos):    {len(limpos) - faixa}")
    print(f"  - preço em faixa (estofados): {faixa}")
    print(f"  - material vazio:           {sem_mat} (inclui {garbled} quebrados saneados)")
    print(f"Arquivo: {os.path.abspath(OUT)}")
    print("\nProdutos por categoria:")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {c}")


if __name__ == "__main__":
    main()
