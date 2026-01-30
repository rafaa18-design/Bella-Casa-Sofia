# Guia de Prompts para Agentes

Como escrever system prompts eficazes para agentes de IA conversacionais usando este template.

## Por Que Prompts Importam

O system prompt é o **contrato comportamental** do agente. Ele define:

- **O que o agente faz** (e o que não faz)
- **Como conversa** (tom, estilo, ritmo)
- **Quando usa ferramentas** (e quais)
- **O que nunca deve acontecer** (limites rígidos)

Um prompt mal escrito gera respostas genéricas, alucinações de funcionalidades, e conversas que parecem um formulário. Um prompt bem escrito gera um agente que parece humano, útil, e confiável.

---

## Anatomia de um Prompt de Agente

Todo prompt de agente deve ter estas seções, nesta ordem:

```
1. IDENTIDADE         — Quem é o agente
2. IDIOMA             — Em que língua responde
3. PRIMEIRA AÇÃO      — O que fazer antes de tudo
4. REGRAS DE DADOS    — O que pode e não pode inventar
5. ESTILO DE CONVERSA — Como falar
6. ATENDIMENTO        — Regras de negócio
7. LIMITAÇÕES         — O que NÃO pode fazer/prometer
8. GESTÃO DE MEMÓRIA  — Quando salvar dados
```

### Por que essa ordem?

O modelo processa instruções sequencialmente. Colocar identidade e idioma primeiro garante que toda resposta subsequente já siga essas regras. Limitações vêm perto do final porque são "guardrails" — o modelo já sabe o que fazer, e agora sabe o que **não** fazer.

---

## Seção por Seção

### 1. IDENTIDADE

Define quem o agente é. Seja específico.

```
❌ Ruim:
"Você é um assistente útil."

✅ Bom:
"Você é a Ana, assistente virtual da Clínica Sorriso, uma clínica
odontológica moderna. Seu papel é atender pacientes com simpatia
e profissionalismo."
```

**Por que funciona:** O modelo ancora seu comportamento na persona. "Assistente útil" é vago — o modelo não sabe se deve ser formal, casual, técnico. "Ana da Clínica Sorriso" dá contexto completo.

**Dicas:**
- Dê um nome ao agente
- Descreva o contexto do negócio
- Defina o papel em uma frase

### 2. IDIOMA

Se o agente deve responder em um idioma específico, declare explicitamente. Modelos tendem a responder no idioma da pergunta — se o system prompt está em português mas o usuário escreve em inglês, o modelo pode alternar.

```
IDIOMA (OBRIGATÓRIO):
- SEMPRE responda em português brasileiro. NUNCA use inglês, nem parcialmente.
- Toda comunicação deve ser 100% em pt-BR.
```

**Dica:** Use "OBRIGATÓRIO" e "NUNCA" para regras invioláveis. Modelos respondem bem a linguagem enfática em restrições.

### 3. PRIMEIRA AÇÃO

Define o que o agente faz **antes de responder ao usuário**. Ideal para chamar tools de contexto automaticamente.

```
PRIMEIRA AÇÃO (OBRIGATÓRIO):
- Na PRIMEIRA mensagem de cada conversa, SEMPRE chame verificar_cliente
  antes de responder
- Essa tool identifica automaticamente se o canal é de um paciente cadastrado
- Se paciente cadastrado: cumprimente pelo nome e use os dados do cadastro
- Se paciente novo: trate como primeiro atendimento, informe avaliação gratuita
- NUNCA pergunte "você já é paciente?" — a verificação é automática
```

**Por que funciona:** Sem essa seção, o agente perguntaria "você já é paciente?" mesmo tendo uma tool que verifica automaticamente. A instrução explícita elimina redundância e melhora a experiência.

**Padrão geral:**
```
PRIMEIRA AÇÃO (OBRIGATÓRIO):
- Na PRIMEIRA mensagem, SEMPRE chame [tool_de_contexto] antes de responder
- Use os dados retornados para personalizar a saudação
- NUNCA peça ao usuário informações que a tool já fornece
```

### 4. REGRAS DE DADOS

A seção mais importante para prevenir alucinações de dados.

```
REGRAS DE DADOS (CRÍTICO - NÃO VIOLAR):
- NUNCA invente, assuma ou deduza dados do paciente
- Só mencione dados pessoais se vieram de verificar_cliente ou do
  CONTEXTO DA SESSÃO
- Se não sabe um dado, PERGUNTE ao paciente. Não adivinhe.
```

**Problema que resolve:** Sem essa regra, o modelo pode "deduzir" dados. Se o paciente disse "moro em São Paulo", o modelo pode inventar um CEP. A regra força o modelo a perguntar em vez de adivinhar.

**Padrão geral:**
```
REGRAS DE DADOS (CRÍTICO - NÃO VIOLAR):
- NUNCA invente dados que não vieram de uma ferramenta ou do usuário
- Só use dados de fontes explícitas: [listar fontes]
- Se não tem a informação, PERGUNTE. Não assuma.
```

### 5. ESTILO DE CONVERSA

Controla o ritmo e a naturalidade da conversa.

```
ESTILO DE CONVERSA:
- Faça UMA ou no máximo DUAS perguntas por mensagem
- Guie a conversa naturalmente, passo a passo
- Não despeje listas longas de perguntas de uma vez
- Seja breve e direto, sem parágrafos longos
- Ordem natural: saudação → entender necessidade → verificar disponibilidade → agendar
```

**Problema que resolve:** Sem essa regra, o modelo tende a fazer 5-6 perguntas de uma vez ("Qual seu nome? CPF? Telefone? E-mail? Convênio? Data preferida?"). Isso não é uma conversa — é um formulário.

**Dicas avançadas:**
- Defina o **fluxo** da conversa (saudação → necessidade → ação)
- Limite perguntas por mensagem (1-2 é ideal)
- Proíba listas longas explicitamente
- Defina tamanho das respostas ("seja breve", "sem parágrafos longos")

### 6. ATENDIMENTO (Regras de Negócio)

Regras específicas do domínio.

```
ATENDIMENTO:
- Antes de agendar, sempre verifique disponibilidade de horários
- Confirme todos os dados com o paciente antes de agendar
- Para novos pacientes, informe que a avaliação inicial é gratuita
- Se o paciente tiver convênio, mencione a cobertura aplicável
- Não forneça diagnósticos ou recomendações médicas
- Em caso de emergência, oriente o paciente a ligar: (11) 3000-1234
```

**Padrão geral:**
```
ATENDIMENTO:
- Antes de [ação principal], sempre [verificação prévia]
- Confirme [dados] com o usuário antes de [executar]
- Para [caso especial], faça [ação diferente]
- NUNCA [ação proibida no domínio]
- Em caso de [situação crítica], oriente [ação segura]
```

### 7. LIMITAÇÕES

**A seção mais subestimada e mais importante.** Sem ela, o agente promete coisas que não pode cumprir.

```
LIMITAÇÕES (CRÍTICO - NÃO VIOLAR):
- NUNCA prometa ou ofereça funcionalidades que você não possui como ferramenta
- Você NÃO pode: enviar SMS, enviar e-mail, enviar WhatsApp, fazer ligações,
  enviar notificações, gerar boletos, processar pagamentos
- Não pergunte se o paciente quer receber confirmação por SMS/e-mail —
  você não tem essa capacidade
- Após agendar, apenas confirme os dados e encerre. Não sugira envio de lembretes
- Só mencione funcionalidades que existem nas suas ferramentas disponíveis
```

**Problema real que resolve:** Sem essa seção, testamos um agente que após agendar uma consulta disse: *"Posso confirmar o envio de lembrete por SMS para (11) 99999-0000? Quer que eu envie também por e-mail?"* — sendo que não existia nenhuma tool de envio de SMS ou e-mail. O modelo inventou a funcionalidade.

**Regra de ouro:** Se o agente não tem uma tool para fazer algo, o prompt deve proibir explicitamente que ele mencione essa capacidade.

**Padrão geral:**
```
LIMITAÇÕES (CRÍTICO - NÃO VIOLAR):
- NUNCA prometa funcionalidades que não existem nas suas ferramentas
- Você NÃO pode: [lista explícita do que NÃO pode]
- Não sugira [ação impossível] — você não tem essa capacidade
- Só mencione funcionalidades que existem nas suas ferramentas disponíveis
```

**Como montar a lista:** Olhe as tools disponíveis, pense no que o usuário pode esperar que o agente faça, e proíba tudo que não está coberto por uma tool.

### 8. GESTÃO DE MEMÓRIA

Instrui o agente sobre quando e como persistir dados.

```
GESTÃO DE MEMÓRIA:
- Use salvar_dados_cliente quando o paciente informar nome, telefone,
  e-mail, CPF ou convênio
- Use salvar_preferencias quando o paciente mencionar horários preferidos,
  dentista preferido, alergias, medos ou qualquer observação relevante
- Use ver_contexto_sessao se precisar relembrar dados já coletados
- Se o CONTEXTO DA SESSÃO estiver presente nas instruções, use esses
  dados e NÃO pergunte novamente ao paciente
- Ao agendar, use os dados do cliente já salvos no contexto da sessão
```

**Por que funciona:** Sem instrução explícita, o agente não sabe quais dados salvar nem quando. Ele pode perguntar o nome do paciente duas vezes na mesma conversa, ou não salvar um dado importante que o usuário mencionou de passagem.

---

## Frameworks de Referência

Ao escrever prompts para agentes, dois frameworks são mais úteis:

### TIDD-EC (Recomendado para agentes)

O mais adequado para agentes conversacionais por ter seções explícitas de "Do" e "Don't":

| Componente | Uso no Agente |
|------------|---------------|
| **T**ask Type | IDENTIDADE — tipo de agente |
| **I**nstructions | ATENDIMENTO — passos do fluxo |
| **D**o | PRIMEIRA AÇÃO, GESTÃO DE MEMÓRIA — o que fazer |
| **D**on't | LIMITAÇÕES, REGRAS DE DADOS — o que não fazer |
| **E**xamples | Exemplos de conversa (few-shot) |
| **C**ontext | Contexto do negócio |

**Por que TIDD-EC:** Agentes precisam de limites claros. A separação explícita de "Do/Don't" mapeia diretamente para o problema de alucinação de funcionalidades.

### RISEN (Para fluxos complexos)

Útil quando o agente tem um fluxo sequencial rígido:

| Componente | Uso no Agente |
|------------|---------------|
| **R**ole | IDENTIDADE |
| **I**nstructions | ESTILO DE CONVERSA |
| **S**teps | ATENDIMENTO — fluxo passo a passo |
| **E**nd Goal | Objetivo do atendimento |
| **N**arrowing | LIMITAÇÕES — restrições |

**Quando usar RISEN:** O agente segue um processo claro (ex: triagem médica com etapas definidas, onboarding com checklist).

### Na prática

O prompt deste template usa uma **abordagem híbrida**: a estrutura de seções nomeadas com tags claras (`IDENTIDADE:`, `LIMITAÇÕES:`) combina os benefícios de ambos os frameworks sem a rigidez de seguir um só.

---

## Padrões e Anti-Padrões

### ✅ Padrões que Funcionam

**Use tags marcadas para seções críticas:**
```
REGRAS DE DADOS (CRÍTICO - NÃO VIOLAR):
```
O texto entre parênteses não é decoração — modelos respondem a indicadores de severidade.

**Seja específico nas proibições:**
```
❌ "Não faça coisas que não pode"
✅ "Você NÃO pode: enviar SMS, enviar e-mail, processar pagamentos"
```

**Defina o fluxo com setas:**
```
Ordem natural: saudação → entender necessidade → verificar disponibilidade → agendar
```

**Instrua por negação quando necessário:**
```
- NUNCA pergunte "você já é paciente?" — a verificação é automática
```
Dizer o que NÃO fazer é tão importante quanto dizer o que fazer. Modelos tendem a comportamentos "óbvios" (perguntar se é cliente recorrente) que podem ser redundantes quando tools automatizam isso.

**Use formatação consistente:**
- Bullets para listas de regras
- MAIÚSCULAS para ênfase em palavras-chave (`SEMPRE`, `NUNCA`, `CRÍTICO`)
- Seções nomeadas com `:` no final

### ❌ Anti-Padrões a Evitar

**Prompt vago:**
```
❌ "Seja útil e profissional. Ajude o usuário no que precisar."
```
O modelo não sabe o que "útil" significa no seu contexto.

**Instruções conflitantes:**
```
❌ "Seja breve e direto" + "Explique detalhadamente cada opção"
```
Escolha um estilo e seja consistente.

**Sem limites de tool:**
```
❌ Não mencionar limitações e esperar que o modelo não invente funcionalidades
```
Se tem 10 tools, o modelo pode inventar a 11ª. Proíba explicitamente.

**Lista de perguntas como fluxo:**
```
❌ "Pergunte: nome, CPF, telefone, e-mail, convênio, data, horário, dentista"
```
Isso vira um formulário. Defina o fluxo como conversa natural.

**Prompt só positivo (sem "Don'ts"):**
```
❌ Só instruções do que fazer, nada sobre o que não fazer
```
Metade das regras de um bom prompt são proibições.

---

## Otimização Iterativa

Prompts devem ser testados e refinados. O ciclo é:

```
Escrever prompt → Testar conversa completa → Identificar falha → Adicionar regra → Repetir
```

### Processo prático

1. **Escreva a v1** com as seções básicas (identidade, estilo, atendimento)
2. **Teste 5-10 conversas** simulando cenários reais
3. **Anote cada falha** — o agente fez algo errado ou indesejado
4. **Categorize as falhas:**
   - Inventou dados? → Adicione em REGRAS DE DADOS
   - Prometeu algo impossível? → Adicione em LIMITAÇÕES
   - Fez muitas perguntas? → Ajuste ESTILO DE CONVERSA
   - Não usou uma tool? → Adicione instrução explícita
   - Usou uma tool errada? → Refine a descrição da tool
5. **Reescreva o prompt** com as novas regras
6. **Repita** até as conversas serem naturais

### Exemplos de falhas reais e correções

| Falha observada | Causa | Correção no prompt |
|-----------------|-------|--------------------|
| Agente ofereceu enviar SMS | Sem seção de limitações | Adicionou `LIMITAÇÕES` com lista explícita |
| Perguntou "você é paciente?" | Não sabia que tool verifica automaticamente | Adicionou `PRIMEIRA AÇÃO` com instrução de usar `verificar_cliente` |
| Fez 6 perguntas de uma vez | Sem limite de perguntas | Adicionou "Faça UMA ou no máximo DUAS perguntas por mensagem" |
| Inventou nome de dentista | Sem regra de dados | Adicionou "NUNCA invente dados que não vieram de uma ferramenta" |
| Misturou idiomas | System prompt em PT mas sem regra explícita | Adicionou seção `IDIOMA (OBRIGATÓRIO)` |

---

## Template Genérico

Use este template como ponto de partida para qualquer agente:

```
Você é [NOME], [CARGO/PAPEL] da [EMPRESA/CONTEXTO].
Seu papel é [OBJETIVO PRINCIPAL] com [ADJETIVOS DE ESTILO].

IDIOMA (OBRIGATÓRIO):
- SEMPRE responda em [idioma]. NUNCA use [outro idioma].

PRIMEIRA AÇÃO (OBRIGATÓRIO):
- Na PRIMEIRA mensagem, SEMPRE chame [tool_de_contexto] antes de responder
- Use os dados retornados para personalizar a saudação
- NUNCA peça informações que a tool já fornece

REGRAS DE DADOS (CRÍTICO - NÃO VIOLAR):
- NUNCA invente dados que não vieram de uma ferramenta ou do usuário
- Só use dados de fontes explícitas: [listar ferramentas e fontes]
- Se não tem a informação, PERGUNTE. Não assuma.

ESTILO DE CONVERSA:
- Faça UMA ou no máximo DUAS perguntas por mensagem
- Guie a conversa naturalmente, passo a passo
- Seja breve e direto, sem parágrafos longos
- Fluxo: [etapa 1] → [etapa 2] → [etapa 3] → [etapa 4]

ATENDIMENTO:
- Antes de [ação principal], sempre [verificação]
- Confirme [dados] antes de [executar]
- Para [caso especial], faça [ação diferente]
- NUNCA [ação proibida no domínio]
- Em caso de [emergência], oriente [ação segura]

LIMITAÇÕES (CRÍTICO - NÃO VIOLAR):
- NUNCA prometa funcionalidades que não existem nas suas ferramentas
- Você NÃO pode: [lista explícita — SMS, e-mail, pagamentos, etc.]
- Não sugira [ação impossível]
- Só mencione funcionalidades que existem nas suas ferramentas

GESTÃO DE MEMÓRIA:
- Use [tool_salvar] quando o usuário informar [dados pessoais]
- Use [tool_preferencias] quando mencionar [preferências]
- Use [tool_contexto] se precisar relembrar dados já coletados
- Se dados já existem no contexto, NÃO pergunte novamente
```

---

## Prompt vs. Descrição de Tool

O system prompt define **quando** usar tools. A **docstring** da tool define **o que ela faz**. Ambos precisam ser claros e complementares.

| Aspecto | System Prompt | Docstring da Tool |
|---------|---------------|-------------------|
| Escopo | Comportamento geral do agente | O que a tool específica faz |
| Exemplo | "SEMPRE chame verificar_cliente primeiro" | "Verifica se o canal pertence a um paciente cadastrado" |
| Lido por | O modelo, como contexto global | O modelo, ao decidir qual tool chamar |
| Deve conter | Quando usar, fluxo, restrições | Parâmetros, retorno, exemplos |

**Erro comum:** Colocar regras de negócio na docstring da tool em vez de no prompt. A docstring deve ser técnica e objetiva. As regras de quando/como usar ficam no prompt.

---

## Configuração no Template

O prompt é configurado em dois lugares:

### 1. Langfuse (produção)
Gerenciado remotamente via Langfuse Prompt Management. Configure `AGENT_PROMPT_NAME` e `AGENT_PROMPT_LABEL` no `.env`:

```bash
AGENT_PROMPT_NAME=agent-instructions
AGENT_PROMPT_LABEL=production
```

### 2. Fallback (config.py / .env)
Se o Langfuse não estiver disponível, o fallback em `AGENT_INSTRUCTIONS_FALLBACK` é usado. Mantenha-o sempre atualizado:

```bash
# .env
AGENT_INSTRUCTIONS_FALLBACK=Você é a Ana, assistente virtual da...
```

```python
# config.py
AGENT_INSTRUCTIONS_FALLBACK: str = (
    'Você é a Ana, assistente virtual da Clínica Sorriso...'
)
```

**Recomendação:** Use Langfuse para iterar em produção sem deploy. O fallback é a rede de segurança.

Veja [docs/desenvolvimento.md](desenvolvimento.md) para detalhes sobre Langfuse e [docs/culture.md](culture.md) para personalidade do agente.

---

## Checklist de Revisão

Antes de colocar um prompt em produção, verifique:

- [ ] **Identidade** — O agente sabe quem é?
- [ ] **Idioma** — Está forçado explicitamente?
- [ ] **Primeira ação** — Chama a tool de contexto antes de responder?
- [ ] **Dados** — Proíbe inventar/deduzir dados?
- [ ] **Estilo** — Limita perguntas por mensagem?
- [ ] **Fluxo** — Define a ordem natural da conversa?
- [ ] **Limitações** — Lista tudo que o agente NÃO pode fazer?
- [ ] **Memória** — Instrui quando salvar dados?
- [ ] **Tools** — Cada tool tem docstring clara?
- [ ] **Teste** — Rodou 5+ conversas completas sem falhas?
