# -*- coding: utf-8 -*-
"""Extrai a descrição (material/estilo) de cada produto fotografado do catálogo PDF
e grava no fotos_index.json."""
import glob
import json
import os
import re
import unicodedata

from pypdf import PdfReader

RAIZ = os.path.join(os.path.dirname(__file__), "..")
IDX = os.path.join(RAIZ, "app", "static", "fotos_index.json")
cat = glob.glob(os.path.join(RAIZ, "catalogo", "**", "*compressed*CORBELLI*.pdf"), recursive=True)
reader = PdfReader(cat[0])


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


# Texto de cada página (uma vez)
paginas = [(pg.extract_text() or "") for pg in reader.pages]

MAT_KW = ("madeira", "aluminio", "alumínio", "tampo", "estrutura", "pes", "pés",
          "mdf", "pedra", "corda", "tecido", "teca", "laqueado", "vidro", "couro",
          "veludo", "metal", "linho")


def descricao_para(nome):
    # o "modelo" é a última palavra do nome (Chevron, Nuvem...)
    modelo = norm(nome).split()[-1]
    for t in paginas:
        nt = norm(t)
        if modelo in nt and len(modelo) > 3:
            # pega frases com palavra de material, na parte PT (antes de "Design"/EN)
            frases = re.split(r"(?<=[.])\s+", t)
            boas = [f.strip() for f in frases
                    if any(k in norm(f) for k in MAT_KW)
                    and 15 < len(f.strip()) < 180
                    and "Sideboard" not in f and "Coffee" not in f]
            if boas:
                d = re.sub(r"\s+", " ", boas[0]).strip()
                # Remove número de página e "A C L" no início
                d = re.sub(r"^\d+\s*", "", d)
                d = re.sub(r"^(A\s+C\s+L\s+)", "", d)
                return d.strip()
    return ""


# Fallbacks curados para produtos sem descrição no PDF
CURADAS = {
    "Mesa lateral Topo": "Mesa lateral da linha 2026, design contemporâneo e acabamento premium.",
}

index = json.load(open(IDX, encoding="utf-8"))
com, sem = 0, []
for it in index:
    d = descricao_para(it["nome"]) or CURADAS.get(it["nome"], "")
    it["descricao"] = d
    if d:
        com += 1
    else:
        sem.append(it["nome"])

json.dump(index, open(IDX, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"Descrições extraídas: {com} de {len(index)}")
print(f"Sem descrição (vou curar manualmente): {len(sem)}")
print("Amostra:")
for it in index[:6]:
    print(f"  {it['nome']}: {it['descricao'][:90] or '(vazio)'}")
if sem:
    print("Sem descrição:", ", ".join(sem[:20]))
