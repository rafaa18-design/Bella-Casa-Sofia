# Few-Shot Learning

Few-shot learning permite ensinar padroes de resposta ao agente atraves de exemplos. Ao fornecer pares de input/output de exemplo, o modelo aprende o formato, tom e estrutura esperados nas respostas.

---

## Abordagens Disponiveis

Few-shot examples podem ser adicionados de duas formas:
1. **Diretamente no system prompt** via `build_system_messages()` em `app/agent.py`
2. **No template Langfuse** via gestao de prompts

---

## Como Implementar

### 1. Exemplos no System Prompt

A forma mais direta -- inclua exemplos no system prompt:

```python
# app/agent.py

FEW_SHOT_EXAMPLES = """
## Exemplos de Resposta

### Exemplo 1: Reset de senha
**Usuario:** Esqueci minha senha e nao consigo entrar
**Assistente:** Vou ajuda-lo a redefinir sua senha imediatamente.

**Passos para Redefinir:**
1. Va para a pagina de login e clique em "Esqueci a Senha"
2. Digite seu email
3. Verifique sua caixa de entrada (e spam)
4. Clique no link de redefinicao
5. Crie uma nova senha forte

Se nao receber o email em 5 minutos, verifique a pasta de spam.
Posso ajudar com mais alguma coisa?

### Exemplo 2: Problema de cobranca
**Usuario:** Fui cobrado duas vezes pelo mesmo pedido!
**Assistente:** Peco sinceras desculpas pelo erro de cobranca.

**Plano de Acao Imediato:**
1. Vou investigar sua conta para confirmar a cobranca duplicada
2. Processar reembolso completo da transacao duplicada
3. Verificar configuracoes de pagamento
4. Fornecer numero de confirmacao do reembolso

O reembolso aparece em 3-5 dias uteis.
Posso ajudar com mais alguma coisa?
"""


def build_system_messages(
    instructions: str,
    text_message: str,
    few_shot_examples: str | None = None,
    **kwargs,
) -> list[dict]:
    """Build messages com few-shot examples."""
    if few_shot_examples:
        instructions = f"{instructions}\n\n{few_shot_examples}"

    messages = [{"role": "system", "content": instructions}]
    # ... resto da construcao
    return messages
```

### 2. Exemplos como Mensagens de Conversa

Mais eficaz para muitos modelos -- injetar exemplos como pares user/assistant:

```python
# app/agent.py

FEW_SHOT_MESSAGES = [
    {"role": "user", "content": "Esqueci minha senha e nao consigo entrar"},
    {"role": "assistant", "content": (
        "Vou ajuda-lo a redefinir sua senha imediatamente.\n\n"
        "**Passos para Redefinir:**\n"
        "1. Va para a pagina de login e clique em 'Esqueci a Senha'\n"
        "2. Digite seu email\n"
        "3. Verifique sua caixa de entrada (e spam)\n"
        "4. Clique no link de redefinicao\n"
        "5. Crie uma nova senha forte\n\n"
        "Posso ajudar com mais alguma coisa?"
    )},
    {"role": "user", "content": "Fui cobrado duas vezes pelo mesmo pedido!"},
    {"role": "assistant", "content": (
        "Peco sinceras desculpas pelo erro de cobranca.\n\n"
        "**Plano de Acao Imediato:**\n"
        "1. Investigar sua conta para confirmar a cobranca duplicada\n"
        "2. Processar reembolso completo da transacao duplicada\n"
        "3. Verificar configuracoes de pagamento\n"
        "4. Fornecer numero de confirmacao do reembolso\n\n"
        "O reembolso aparece em 3-5 dias uteis."
    )},
]


def build_system_messages(
    instructions: str,
    text_message: str,
    few_shot: list[dict] | None = None,
    images: list[dict] | None = None,
    history: list[dict] | None = None,
) -> list[dict]:
    messages = [{"role": "system", "content": instructions}]

    # Injetar exemplos few-shot (antes do historico real)
    if few_shot:
        messages.extend(few_shot)

    # Historico da conversa
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content and role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

    # Mensagem atual do usuario
    messages.append({"role": "user", "content": text_message})

    return messages
```

### 3. Few-Shot no Template Langfuse

Adicione exemplos diretamente no prompt template gerenciado pelo Langfuse:

```
Voce e um especialista em suporte ao cliente.
Seja empatico, profissional e focado em solucoes.

## Exemplos de Resposta

### Problema de acesso
**Usuario:** Nao consigo acessar minha conta
**Resposta esperada:**
1. Verificar identidade do usuario
2. Diagnosticar tipo de bloqueio
3. Resolver com passos claros
4. Confirmar resolucao

### Reclamacao
**Usuario:** Estou insatisfeito com o servico
**Resposta esperada:**
1. Pedir desculpas genuinamente
2. Entender o problema especifico
3. Propor solucao concreta
4. Oferecer compensacao se aplicavel

Siga estes padroes ao responder.
{{context}}
```

O template e gerenciado via `app/prompt_manager.py` e atualizado pelo webhook `/prompts/webhook`.

### 4. Few-Shot com Structured Output

Para respostas estruturadas, inclua exemplos do formato esperado:

```python
# Exemplos no system prompt ou Langfuse template

STRUCTURED_FEW_SHOT = """
## Formato de Resposta

Sempre responda no seguinte formato JSON:

Exemplo 1:
Input: "Adorei o produto! Chegou antes do prazo."
Output: {"sentimento": "positivo", "confianca": 0.95, "topicos": ["entrega", "qualidade"]}

Exemplo 2:
Input: "Pessimo atendimento, esperei 2 horas"
Output: {"sentimento": "negativo", "confianca": 0.92, "topicos": ["atendimento", "tempo"]}

Exemplo 3:
Input: "O produto e ok, faz o que promete"
Output: {"sentimento": "neutro", "confianca": 0.75, "topicos": ["produto"]}
"""
```

---

## Boas Praticas

| Pratica | Descricao |
|---------|-----------|
| **3-5 exemplos** | Quantidade ideal para a maioria dos casos |
| **Exemplos diversos** | Cubra diferentes cenarios e edge cases |
| **Formato consistente** | Mantenha estrutura similar em todos os exemplos |
| **Exemplos realistas** | Use casos reais ou muito proximos da realidade |
| **Mensagens user/assistant** | Mais eficaz que exemplos no system prompt para muitos modelos |

---

## Resumo

| Funcionalidade | Como Implementar |
|----------------|------------------|
| Exemplos de conversa | Lista de dicts `{"role": ..., "content": ...}` em `build_system_messages()` |
| Mensagem de exemplo | `{"role": "user", "content": ...}` (formato LiteLLM) |
| Few-shot em multi-agent | Injetar exemplos no system prompt de cada agente individualmente |
| Atualizacao de exemplos | Gerenciar via template Langfuse (`/prompts/webhook`) |
