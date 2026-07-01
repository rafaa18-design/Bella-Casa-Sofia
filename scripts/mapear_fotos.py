# -*- coding: utf-8 -*-
"""Mapeia as fotos por produto: caminho, contagem, tamanho. Decide hospedagem."""
import os

BASE = r"c:/Users/rafaa/OneDrive/Desktop/Bella Casa/asani-ai-agent-template/catalogo/fotos"
IMG_EXT = (".jpg", ".jpeg", ".png")

produtos = {}
total_bytes = 0
total_imgs = 0
for root, dirs, files in os.walk(BASE):
    imgs = [f for f in files if f.lower().endswith(IMG_EXT)]
    if not imgs:
        continue
    # nome do produto = pasta imediatamente após uma categoria; usa o 1º nível abaixo de fotos
    rel = os.path.relpath(root, BASE)
    partes = rel.split(os.sep)
    produto = partes[1] if len(partes) >= 2 else partes[0]
    d = produtos.setdefault(produto, {"n": 0, "bytes": 0, "amostra": ""})
    for im in imgs:
        p = os.path.join(root, im)
        sz = os.path.getsize(p)
        d["n"] += 1
        d["bytes"] += sz
        total_bytes += sz
        total_imgs += 1
        if not d["amostra"]:
            d["amostra"] = os.path.relpath(p, BASE)

print(f"Produtos com foto: {len(produtos)}")
print(f"Total de imagens: {total_imgs}  |  Total: {total_bytes/1024/1024:.1f} MB")
print(f"Media por imagem: {total_bytes/max(total_imgs,1)/1024:.0f} KB")
print("\nAmostra (5 produtos):")
for nome, d in list(produtos.items())[:5]:
    print(f"  {nome}: {d['n']} imgs, {d['bytes']/1024:.0f} KB | ex: {d['amostra']}")
