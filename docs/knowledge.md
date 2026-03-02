# Knowledge Bases e RAG

RAG (Retrieval-Augmented Generation) permite que o agente consulte bases de conhecimento externas para responder perguntas com informacoes atualizadas e especificas do dominio. O agente busca documentos relevantes em um banco vetorial e usa o conteudo como contexto.

---

## Abordagem

RAG e implementado como uma **tool que consulta um banco de dados vetorial** (pgvector, Pinecone, ChromaDB, etc.) e retorna contexto relevante para o agente.

---

## Como Implementar

### 1. RAG como Tool (Agentic RAG)

O agente decide quando buscar no knowledge base -- esta e a abordagem recomendada:

```python
# app/tools/knowledge.py

"""Tool: buscar_conhecimento -- Busca na base de conhecimento vetorial."""

from app.runtime import tool


@tool
def buscar_conhecimento(query: str, top_k: int = 5) -> str:
    """Busca informacoes relevantes na base de conhecimento.

    Use esta ferramenta quando precisar de informacoes especificas
    sobre documentos, politicas ou procedimentos da empresa.

    Args:
        query: Pergunta ou termo de busca.
        top_k: Numero maximo de resultados.
    """
    # Exemplo com pgvector (PostgreSQL)
    import asyncio
    results = asyncio.get_event_loop().run_until_complete(
        _buscar_pgvector(query, top_k)
    )
    if not results:
        return "Nenhum documento relevante encontrado."

    formatted = []
    for i, doc in enumerate(results, 1):
        formatted.append(f"[{i}] {doc['content'][:500]}")

    return "\n\n".join(formatted)


async def _buscar_pgvector(query: str, top_k: int) -> list[dict]:
    """Busca vetorial usando pgvector."""
    import asyncpg
    import openai

    # Gerar embedding da query
    client = openai.AsyncOpenAI()
    embedding_response = await client.embeddings.create(
        input=query,
        model="text-embedding-3-small",
    )
    query_embedding = embedding_response.data[0].embedding

    # Buscar no pgvector
    conn = await asyncpg.connect("postgresql://user:pass@localhost/db")
    rows = await conn.fetch(
        """
        SELECT content, metadata,
               1 - (embedding <=> $1::vector) AS similarity
        FROM documents
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        str(query_embedding),
        top_k,
    )
    await conn.close()

    return [{"content": r["content"], "similarity": r["similarity"]} for r in rows]
```

### 2. RAG Tradicional (Contexto no Prompt)

Alternativa: sempre injetar contexto relevante no system prompt:

```python
# app/agent.py

async def build_system_messages_with_rag(
    instructions: str,
    text_message: str,
    images: list[dict] | None = None,
    history: list[dict] | None = None,
) -> list[dict]:
    """Build messages com contexto RAG injetado automaticamente."""
    from app.tools.knowledge import _buscar_pgvector

    # Buscar contexto relevante
    docs = await _buscar_pgvector(text_message, top_k=3)

    if docs:
        context = "\n\n".join(d["content"][:500] for d in docs)
        instructions = (
            f"{instructions}\n\n"
            f"## Contexto Relevante (Base de Conhecimento)\n{context}"
        )

    messages = [{"role": "system", "content": instructions}]
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": text_message})
    return messages
```

### 3. Exemplo com Pinecone

```python
# app/tools/knowledge_pinecone.py

from app.runtime import tool


@tool
def buscar_conhecimento(query: str, top_k: int = 5) -> str:
    """Busca informacoes na base de conhecimento via Pinecone.

    Args:
        query: Pergunta ou termo de busca.
        top_k: Numero maximo de resultados.
    """
    import openai
    from pinecone import Pinecone

    # Gerar embedding
    client = openai.OpenAI()
    embedding = client.embeddings.create(
        input=query, model="text-embedding-3-small"
    ).data[0].embedding

    # Buscar no Pinecone
    pc = Pinecone()
    index = pc.Index("meu-indice")
    results = index.query(vector=embedding, top_k=top_k, include_metadata=True)

    if not results.matches:
        return "Nenhum documento relevante encontrado."

    formatted = []
    for match in results.matches:
        score = f"{match.score:.2f}"
        content = match.metadata.get("content", "")[:500]
        formatted.append(f"[Score: {score}] {content}")

    return "\n\n".join(formatted)
```

### 4. Registrar a Tool

```python
# app/agent.py

from app.tools.knowledge import buscar_conhecimento


def get_tools_registry() -> ToolRegistry:
    registry = ToolRegistry()

    all_tools = [
        # ... tools existentes
        buscar_conhecimento,  # Tool de RAG
    ]

    for t in all_tools:
        registry.register(t)

    return registry
```

---

## Tipos de Busca

| Tipo | Descricao | Quando Usar |
|------|-----------|-------------|
| **Vetorial** | Similaridade semantica (cosine/L2) | Perguntas conceituais |
| **Keyword** | Busca por palavras-chave (BM25) | Termos especificos, nomes |
| **Hibrida** | Combina vetorial + keyword | Melhor precisao geral |

---

## Embedders Comuns

| Modelo | Dimensoes | Uso |
|--------|-----------|-----|
| `text-embedding-3-small` (OpenAI) | 1536 | Geral, rapido, baixo custo |
| `text-embedding-3-large` (OpenAI) | 3072 | Alta precisao |
| `embed-v4.0` (Cohere) | 1024 | Multilingual |
| `nomic-embed-text` (Ollama) | 768 | Local, privado, gratuito |

---

## Resumo

| Funcionalidade | Como Implementar |
|----------------|------------------|
| Banco vetorial | Tool que consulta pgvector/Pinecone diretamente |
| Agentic RAG | Tool `buscar_conhecimento` com `@tool` decorator |
| Traditional RAG | Injetar contexto no system prompt via `build_system_messages()` |
| Embeddings | `openai.embeddings.create()` direto |
| Busca hibrida | Implementar busca hibrida no SQL/servico vetorial |
