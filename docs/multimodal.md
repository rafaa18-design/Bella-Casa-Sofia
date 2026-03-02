# Multimodal (Imagens, Audio, Video)

O sistema suporta entrada multimodal via o modelo `InputItem` e a funcao `parse_multimodal_input()` em `app/main.py`. Imagens sao enviadas ao LLM no formato OpenAI Vision (via LiteLLM). Audio e transcrito para texto via API Whisper da OpenAI.

---

## Conceitos

| Conceito | Descricao |
|----------|-----------|
| **InputItem** | Modelo Pydantic para cada item de entrada (texto, imagem, audio, documento, video) |
| **parse_multimodal_input()** | Funcao que converte `list[InputItem]` em `(text, list[dict])` para o LiteLLM |
| **transcribe_audio()** | Transcreve audio em texto usando a API OpenAI Whisper |
| **Content Parts** | Formato OpenAI Vision usado pelo LiteLLM para imagens inline |

---

## Modelo InputItem

Cada item de entrada segue o schema `InputItem` definido em `app/models.py`:

```python
from pydantic import BaseModel, Field
from typing import Literal

InputType = Literal['text', 'image', 'audio', 'document', 'video']

class InputItem(BaseModel):
    """Item de entrada multimodal."""
    type: InputType = Field(..., description='Tipo do conteudo: text, image, audio, document, video')
    content: str = Field(..., description='Texto puro ou conteudo codificado em base64')
    filename: str | None = Field(None, description='Nome original do arquivo (para conteudo nao-texto)')
    mime_type: str | None = Field(None, description='Tipo MIME (ex: image/png)')
```

Uma requisicao envia uma lista de `InputItem` (maximo 20):

```python
class RunRequest(BaseModel):
    input: list[InputItem] = Field(..., min_length=1, max_length=20)
    conversation_id: str = Field(..., min_length=1)
    model: str | None = Field(None, description='Override opcional de modelo')
```

---

## Fluxo de Processamento

```
Request.input (list[InputItem])
    |
    v
parse_multimodal_input(items)
    |
    +-- type == 'text'   --> concatena em text_parts
    +-- type == 'image'  --> decodifica base64, monta content part OpenAI Vision
    +-- type == 'audio'  --> decodifica base64, transcribe_audio() --> texto
    +-- type == 'video'  --> nota textual (nao suportado nativamente)
    +-- type == 'document' --> nota textual com filename
    |
    v
Retorna (text_message: str, images: list[dict])
    |
    v
build_system_messages(instructions, text_message, images, history)
    |
    v
litellm.acompletion(messages=...) via run_agent_loop()
```

---

## Imagens

Imagens sao enviadas como base64 no campo `content` do `InputItem`. A funcao `parse_multimodal_input()` converte para o formato OpenAI Vision que o LiteLLM aceita.

### Formato de Entrada (Request JSON)

```json
{
  "input": [
    {"type": "text", "content": "O que voce ve nesta imagem?"},
    {
      "type": "image",
      "content": "iVBORw0KGgoAAAANSUhEUgAA...",
      "filename": "foto.png",
      "mime_type": "image/png"
    }
  ],
  "conversation_id": "conv-123"
}
```

### Conversao Interna (parse_multimodal_input)

```python
# Trecho de app/main.py - parse_multimodal_input()
elif item.type == 'image':
    content_bytes = base64.b64decode(item.content)
    b64_str = base64.b64encode(content_bytes).decode('utf-8')
    mime = item.mime_type or 'image/jpeg'
    images.append({
        'type': 'image_url',
        'image_url': {'url': f'data:{mime};base64,{b64_str}'},
    })
```

A imagem e montada como um content part no formato padrao:

```python
{
    "type": "image_url",
    "image_url": {"url": "data:image/png;base64,iVBORw0KGgo..."}
}
```

### Montagem da Mensagem (build_system_messages)

Quando ha imagens, a mensagem do usuario usa o formato multimodal do LiteLLM:

```python
# Trecho de app/agent.py - build_system_messages()
if images:
    content_parts = [{'type': 'text', 'text': text_message}]
    content_parts.extend(images)
    messages.append({'role': 'user', 'content': content_parts})
else:
    messages.append({'role': 'user', 'content': text_message})
```

### Multiplas Imagens

Basta enviar multiplos `InputItem` com `type: "image"`. Todos serao adicionados como content parts na mesma mensagem:

```json
{
  "input": [
    {"type": "text", "content": "Compare estas duas imagens."},
    {"type": "image", "content": "base64_imagem_1...", "mime_type": "image/jpeg"},
    {"type": "image", "content": "base64_imagem_2...", "mime_type": "image/jpeg"}
  ],
  "conversation_id": "conv-456"
}
```

---

## Audio

Audio nao e enviado nativamente ao LLM. Em vez disso, e transcrito para texto via API OpenAI Whisper e o resultado e concatenado ao texto do usuario.

### Transcricao com Whisper (transcribe_audio)

```python
# Trecho de app/main.py - transcribe_audio()
def transcribe_audio(audio_bytes: bytes, mime_type: str | None = None) -> str:
    """Transcreve audio em texto usando a API OpenAI Whisper."""
    ext = '.mp3'
    if mime_type:
        ext_map = {'audio/ogg': '.ogg', 'audio/mpeg': '.mp3', 'audio/wav': '.wav'}
        ext = ext_map.get(mime_type, '.mp3')

    with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as f:
        f.write(audio_bytes)
        f.flush()
        with open(f.name, 'rb') as audio_file:
            resp = httpx.post(
                'https://api.openai.com/v1/audio/transcriptions',
                headers={'Authorization': f'Bearer {settings.OPENAI_API_KEY}'},
                files={'file': (f'audio{ext}', audio_file)},
                data={'model': 'gpt-4o-mini-transcribe', 'language': 'pt'},
                timeout=30.0,
            )
            if resp.status_code == 200:
                return resp.json().get('text', '')
            return '[audio nao transcrito]'
```

### Fluxo no parse_multimodal_input

```python
elif item.type == 'audio':
    content_bytes = base64.b64decode(item.content)
    transcription = transcribe_audio(content_bytes, item.mime_type)
    if transcription:
        text_parts.append(f'[Audio do usuario]: {transcription}')
```

O texto transcrito e injetado na mensagem do usuario com o prefixo `[Audio do usuario]:`, permitindo que o LLM entenda que aquele conteudo veio de uma entrada de voz.

### Exemplo de Request com Audio

```json
{
  "input": [
    {
      "type": "audio",
      "content": "UklGRiQAAABXQVZFZm10IBAAAA...",
      "filename": "mensagem.ogg",
      "mime_type": "audio/ogg"
    }
  ],
  "conversation_id": "conv-789"
}
```

### Formatos Suportados

| Formato | MIME Type | Extensao |
|---------|-----------|----------|
| MP3 | audio/mpeg | .mp3 |
| WAV | audio/wav | .wav |
| OGG | audio/ogg | .ogg |

---

## Video

Video nao e suportado nativamente para analise direta. Quando um `InputItem` com `type: "video"` e recebido, uma nota textual e adicionada ao contexto:

```python
elif item.type == 'video':
    text_parts.append('[Video enviado pelo usuario - nao suportado para analise direta]')
```

---

## Documentos

Documentos tambem nao sao processados diretamente. Uma nota com o nome do arquivo e adicionada:

```python
elif item.type == 'document':
    text_parts.append(f'[Documento enviado: {item.filename or "documento"}]')
```

---

## Suporte por Tipo de Entrada

| Tipo | Processamento | Enviado ao LLM |
|------|--------------|----------------|
| **text** | Direto | Sim, como texto |
| **image** | Base64 para content part | Sim, formato OpenAI Vision |
| **audio** | Whisper API para texto | Sim, como texto transcrito |
| **video** | Nota textual | Apenas nota informativa |
| **document** | Nota textual | Apenas nota informativa |

---

## Formatos de Imagem Aceitos

Declarados no endpoint `/metadata`:

```python
input_types=InputTypes(
    supported_types=['text', 'image', 'audio'],
    allowed_formats={
        'image': ['jpeg', 'jpg', 'png', 'webp'],
        'audio': ['mp3', 'wav', 'ogg'],
    },
)
```

---

## Exemplo Completo: Request Multimodal

```json
{
  "input": [
    {"type": "text", "content": "Analise esta imagem e me diga o que voce ve."},
    {
      "type": "image",
      "content": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
      "mime_type": "image/png",
      "filename": "captura.png"
    }
  ],
  "conversation_id": "sessao-001",
  "model": "claude-sonnet-4-20250514"
}
```

Resultado interno apos `parse_multimodal_input()`:

```python
text_message = "Analise esta imagem e me diga o que voce ve."
images = [
    {
        "type": "image_url",
        "image_url": {
            "url": "data:image/png;base64,iVBORw0KGgoAAAANSUh..."
        }
    }
]
```

Mensagem final enviada ao LiteLLM:

```python
[
    {"role": "system", "content": "...instrucoes do agente..."},
    # ...historico de conversas anteriores...
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "Analise esta imagem e me diga o que voce ve."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
        ]
    }
]
```

---

## Referencias

- [LiteLLM Vision/Image Support](https://docs.litellm.ai/docs/completion/vision)
- [OpenAI Vision API](https://platform.openai.com/docs/guides/vision)
- [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text)
