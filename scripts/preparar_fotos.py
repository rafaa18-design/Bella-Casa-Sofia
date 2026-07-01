# -*- coding: utf-8 -*-
"""Escolhe 1 foto por produto, redimensiona p/ WhatsApp e gera o índice.

Saída:
  app/static/fotos/<slug>.jpg   (imagens leves ~1080px)
  catalogo/fotos_index.json     ({slug, nome, categoria, foto})
"""
import json
import os
import re
import unicodedata

from PIL import Image

RAIZ = os.path.join(os.path.dirname(__file__), "..")
BASE = os.path.join(RAIZ, "catalogo", "fotos")
OUT_IMG = os.path.join(RAIZ, "app", "static", "fotos")
OUT_JSON = os.path.join(RAIZ, "app", "static", "fotos_index.json")
# Recria a pasta do zero (remove slugs errados de execuções anteriores)
if os.path.isdir(OUT_IMG):
    for f in os.listdir(OUT_IMG):
        os.remove(os.path.join(OUT_IMG, f))
os.makedirs(OUT_IMG, exist_ok=True)

IMG_EXT = (".jpg", ".jpeg", ".png")
MAX_LADO = 1080


def eh_midia(nome: str) -> bool:
    n = nome.strip().lower()
    return n.startswith("fotos") or n.startswith("foto ") or n in ("videos", "vídeos", "video", "vídeo")


# Nomes de categoria (não são produtos) — para descartar fotos soltas em categoria
CATEGORIAS_PASTA = {
    "aparadores", "bancos e puffs", "bares", "buffets", "cadeiras", "conjuntos",
    "espelhos", "mesas de centro", "mesas de jantar", "mesas laterais", "poltronas",
    "00 lançamentos 2026",
}


def slug(nome):
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s


def produto_de(path):
    """Nome do produto = pasta ancestral que não é mídia nem categoria."""
    partes = os.path.relpath(path, BASE).split(os.sep)[:-1]  # sem o arquivo
    # da mais profunda para a mais rasa, acha a 1ª que não é mídia nem categoria
    for nome in reversed(partes):
        if eh_midia(nome) or nome.strip().lower() in CATEGORIAS_PASTA:
            continue
        return nome
    return ""


# Coleta candidatas por produto (prefere "Fotos em loja" = menor/foco no produto)
cand = {}
for root, _dirs, files in os.walk(BASE):
    for f in files:
        if not f.lower().endswith(IMG_EXT):
            continue
        p = os.path.join(root, f)
        prod = produto_de(p)
        if not prod or prod.strip().lower() in CATEGORIAS_PASTA:
            continue
        em_loja = "loja" in root.lower()
        cand.setdefault(prod, []).append((0 if em_loja else 1, os.path.getsize(p), p))

index = []
for prod, lst in sorted(cand.items()):
    lst.sort()  # loja primeiro, depois menor tamanho
    escolhida = lst[0][2]
    sl = slug(prod)
    try:
        img = Image.open(escolhida).convert("RGB")
        img.thumbnail((MAX_LADO, MAX_LADO))
        img.save(os.path.join(OUT_IMG, f"{sl}.jpg"), "JPEG", quality=82, optimize=True)
    except Exception as e:  # noqa: BLE001
        print(f"  [erro] {prod}: {e}")
        continue
    categoria = slug(prod.split()[0]) if prod else ""
    index.append({"slug": sl, "nome": prod, "categoria": categoria, "foto": f"fotos/{sl}.jpg"})

with open(OUT_JSON, "w", encoding="utf-8") as fp:
    json.dump(index, fp, ensure_ascii=False, indent=2)

tot = sum(os.path.getsize(os.path.join(OUT_IMG, f)) for f in os.listdir(OUT_IMG))
print(f"Produtos com foto preparada: {len(index)}")
print(f"Tamanho total das fotos leves: {tot/1024/1024:.1f} MB")
print("Amostra:")
for it in index[:6]:
    print(f"  {it['nome']}  ->  {it['foto']}  (cat: {it['categoria']})")
