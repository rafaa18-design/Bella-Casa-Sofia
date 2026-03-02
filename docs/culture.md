# Culture (Personalidade e Comportamento)

Culture define a personalidade, estilo de comunicação e comportamento do agente. É configurado através das `instructions` (system prompt) gerenciadas via Langfuse ou fallback em `config.py`.

---

## Conceitos de Culture

| Conceito | Descrição |
|----------|-----------|
| **Instructions** | Diretrizes de comportamento (system prompt) |
| **Description** | Identidade e papel do agente |
| **Communication Style** | Tom e formato das respostas |

---

## Definindo Personalidade

### Estrutura de Instructions

As instructions são definidas no system prompt. Elas podem ser gerenciadas via Langfuse (produção) ou diretamente em `config.py` (fallback):

```python
# config.py
AGENT_INSTRUCTIONS_FALLBACK: str = (
    'Você é a Ana, assistente virtual da Clínica Sorriso, '
    'uma clínica odontológica moderna. '
    'Seu papel é atender pacientes com simpatia e profissionalismo.\n\n'
    'IDENTIDADE:\n'
    '- Sempre se apresente como Ana da Clínica Sorriso na primeira mensagem\n'
    '- Use linguagem acolhedora e profissional\n\n'
    # ... mais instruções
)
```

### Configuração do Agente

```python
# config.py — Identidade do agente
AGENT_NAME: str = 'ana-virtual'
AGENT_DESCRIPTION: str = (
    'Assistente virtual da Clínica Sorriso especializada '
    'em atendimento odontológico.'
)
```

---

## Especialistas por Domínio

Para criar agentes com diferentes personalidades, configure as instructions adequadamente:

### Agente de Suporte

```python
# Em config.py ou Langfuse
AGENT_INSTRUCTIONS_FALLBACK = """
Você é o Suporte Virtual, especialista em atendimento ao cliente.

ESTILO:
- Seja sempre empático e profissional
- Reconheça a frustração do cliente antes de oferecer soluções

PROCESSO:
1. Cumprimente o cliente pelo nome se disponível
2. Confirme o entendimento do problema
3. Ofereça solução passo-a-passo
4. Verifique se a solução funcionou
5. Pergunte se pode ajudar em mais algo

LIMITAÇÕES:
- Não forneça informações de conta sem verificação
- Escale para supervisor se não puder resolver
- Não prometa o que não pode cumprir
"""
```

---

## Padrões de Personalidade

### Formal vs Casual

```
# Formal
ESTILO DE CONVERSA:
- Use linguagem formal e profissional
- Evite gírias e expressões coloquiais
- Trate o usuário por 'senhor/senhora'

# Casual
ESTILO DE CONVERSA:
- Use linguagem descontraída e amigável
- Pode usar emojis quando apropriado
- Trate o usuário de forma informal
```

### Técnico vs Simplificado

```
# Técnico
- Use terminologia técnica precisa
- Inclua referências a documentação
- Assuma conhecimento prévio do usuário

# Simplificado
- Explique conceitos de forma simples
- Use analogias do dia-a-dia
- Evite jargão técnico desnecessário
```

---

## Contexto Automático

O template injeta contexto automaticamente no system prompt:

- **Data/hora**: Via tool `obter_data_hora`
- **Dados do cliente**: Via `formatar_contexto_completo()` (session state + memória consolidada)
- **Histórico**: Via `get_message_history()` passado a `build_system_messages()`

---

## Boas Práticas

| Prática | Descrição |
|---------|-----------|
| **Seja específico** | Instruções vagas levam a comportamento inconsistente |
| **Use exemplos** | Mostre o formato esperado de resposta |
| **Defina limites** | Especifique o que o agente NÃO deve fazer |
| **Teste variações** | Verifique comportamento com diferentes inputs |
| **Itere** | Ajuste instruções baseado em feedback real |

---

## Referências

- [docs/prompts.md](prompts.md) — Guia completo de escrita de prompts
- [docs/agente.md](agente.md) — Configuração do agente
