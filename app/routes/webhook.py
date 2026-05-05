"""Webhook do UazAPI — entrada de mensagens do WhatsApp para a Valentina."""
import asyncio
import logging
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from app.agent import build_system_messages, get_litellm_model, get_tools_registry, run_agent_loop
from app.prompt_manager import get_agent_instructions
from app.routes.firebase_api import load_conversation_history, save_conversation_message
from app.runtime import RunContext

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/webhook', tags=['webhook'])

UAZAPI_URL = os.getenv('UAZAPI_URL', '')
UAZAPI_TOKEN = os.getenv('UAZAPI_TOKEN', '')

# Histórico em memória por sessão (substituir por Redis em produção)
_history: dict[str, list[dict]] = {}
_last_activity: dict[str, datetime] = {}
_reminder_sent: set[str] = set()

INACTIVITY_REMINDER_MIN = 10
INACTIVITY_CLOSE_MIN = 20


async def _inactivity_monitor() -> None:
    """Verifica sessões inativas a cada minuto e envia lembrete ou encerra."""
    while True:
        await asyncio.sleep(60)
        now = datetime.now(timezone.utc)
        for phone in list(_last_activity.keys()):
            if phone not in _history:
                _last_activity.pop(phone, None)
                _reminder_sent.discard(phone)
                continue
            elapsed = (now - _last_activity[phone]).total_seconds() / 60
            if elapsed >= INACTIVITY_CLOSE_MIN:
                msg = 'Como nao houve retorno, estamos encerrando seu atendimento. Quando quiser, e so nos chamar!'
                await _send_whatsapp(phone, msg)
                await save_conversation_message(phone, '', '', msg, 'encerrado')
                _history.pop(phone, None)
                _last_activity.pop(phone, None)
                _reminder_sent.discard(phone)
                logger.info(f'Sessao encerrada por inatividade: {phone}')
            elif elapsed >= INACTIVITY_REMINDER_MIN and phone not in _reminder_sent:
                msg = 'Ola! Ainda esta por ai? Posso continuar te ajudando com o que precisa na Bella Casa.'
                await _send_whatsapp(phone, msg)
                _reminder_sent.add(phone)
                logger.info(f'Lembrete de inatividade enviado: {phone}')


def start_inactivity_monitor() -> None:
    asyncio.create_task(_inactivity_monitor())


class UazapiMessage(BaseModel):
    phone: str | None = None
    message: str | None = None
    fromMe: bool = False
    type: str = 'text'


def _clean_response(text: str) -> str:
    """Remove markdown, emojis e perguntas extras da resposta antes de enviar ao cliente."""
    # Remove negrito e itálico (**texto**, *texto*, __texto__, _texto_)
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}([^_\n]+)_{1,2}', r'\1', text)
    # Remove hashtags de título (# Título → Título)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove listas numeradas (1. item → item)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    # Remove marcadores de lista (- item, • item)
    text = re.sub(r'^[-•]\s+', '', text, flags=re.MULTILINE)
    # Remove emojis
    text = re.sub(
        r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001FA00-\U0001FA9F'
        r'\U00002702-\U000027B0\U0000FE0F\U0001F1E0-\U0001F1FF]',
        '',
        text,
    )
    # Normaliza espaços extras e linhas em branco
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # Regra de uma pergunta por vez: se houver mais de um "?", corta na primeira
    if text.count('?') > 1:
        first_q = text.index('?')
        text = text[:first_q + 1].strip()

    return text


async def _send_whatsapp(phone: str, text: str):
    """Envia mensagem de volta para o cliente via UazAPI.

    Endpoint correto: POST /send/text
    Campos: number (destino) + text (conteúdo)
    Ref: https://docs.uazapi.com/endpoint/post/send~text
    """
    url = f'{UAZAPI_URL}/send/text'
    if not UAZAPI_URL or not UAZAPI_TOKEN:
        logger.error(
            f'UAZAPI não configurado! UAZAPI_URL={UAZAPI_URL!r}, UAZAPI_TOKEN={"***" if UAZAPI_TOKEN else "VAZIO"}'
        )
        return
    try:
        token_preview = f'{UAZAPI_TOKEN[:6]}...{UAZAPI_TOKEN[-4:]}' if len(UAZAPI_TOKEN) > 10 else '(token curto demais)'
        logger.info(f'Enviando para {phone} via {url} | token={token_preview}')
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={'token': UAZAPI_TOKEN},
                json={'number': phone, 'text': text},
                timeout=10,
            )
        logger.info(f'UazAPI resposta {phone}: status={resp.status_code} body={resp.text[:200]}')
    except Exception as e:
        logger.error(f'Erro ao enviar mensagem UazAPI para {phone}: {e}')


async def _process_message(phone: str, text: str):
    """Processa a mensagem e gera resposta da Sofia."""
    _last_activity[phone] = datetime.now(timezone.utc)
    _reminder_sent.discard(phone)
    history = _history.get(phone, [])

    # Se não há histórico em memória (ex: servidor reiniciou), reconstruir do Firestore
    if not history:
        history = await load_conversation_history(phone)
        if history:
            logger.info(f'Histórico reconstruído do Firestore para {phone}: {len(history)} mensagens')
            _history[phone] = history

    instructions = await get_agent_instructions()
    messages = build_system_messages(
        instructions=instructions,
        text_message=text,
        history=history,
    )

    tools = get_tools_registry()
    model = get_litellm_model()

    run_context = RunContext(
        session_id=phone,
        session_state={'phone': phone},
    )

    response = await run_agent_loop(
        messages=messages,
        tools=tools,
        run_context=run_context,
        model=model,
        max_iterations=10,
        temperature=0.1,
        max_tokens=1024,
    )

    # Handoff completo se a tool foi chamada OU se lead foi registrado e vendedora atribuída
    handoff_complete = run_context.session_state.get('handoff_complete', False) or (
        bool(run_context.session_state.get('lead_id'))
        and bool(run_context.session_state.get('assigned_seller_name'))
    )

    # Se handoff, response.content é o JSON interno do StopAgentRun — não enviar ao cliente
    raw_content = response.content or ''
    is_system_json = raw_content.strip().startswith('{"handoff"')
    farewell = run_context.session_state.get('farewell_message', '')
    if handoff_complete and is_system_json and farewell:
        message_to_send = farewell
    elif handoff_complete and is_system_json:
        message_to_send = ''
    else:
        message_to_send = raw_content

    # Aplica limpeza: remove markdown, emojis e perguntas extras
    clean_content = _clean_response(message_to_send) if message_to_send else ''
    logger.info(f'Resposta limpa para {phone}: {clean_content[:120]}')

    # Salva histórico em memória com a versão limpa (últimas 20 mensagens)
    history.append({'role': 'user', 'content': text})
    if clean_content:
        history.append({'role': 'assistant', 'content': clean_content})
    _history[phone] = history[-20:]

    # Determina estágio e persiste conversa no Firestore (versão limpa)
    stage = 'encerrado' if handoff_complete else 'qualificacao'
    lead_id = run_context.session_state.get('lead_id', '')
    await save_conversation_message(phone, lead_id, text, clean_content or '[handoff]', stage)

    # Se handoff completo, limpa histórico em memória para próxima conversa
    if handoff_complete:
        _history.pop(phone, None)
        _last_activity.pop(phone, None)
        _reminder_sent.discard(phone)

    if clean_content:
        await _send_whatsapp(phone, clean_content)


def _parse_uazapi_body(body: dict) -> tuple[str, str, bool, bool]:
    """Extrai phone, text, fromMe e isGroup do payload do UazAPI.

    Retorna: (phone, text, from_me, is_group)
    Se não reconhecido: ('', '', False, False)
    """
    import json

    logger.info(f'UAZAPI_BODY: {json.dumps(body)[:500]}')

    # Formato Evolution API / free.uazapi.com (campo "data" na raiz)
    data = body.get('data', {})
    if data:
        key = data.get('key', {})
        from_me = key.get('fromMe', False)
        remote_jid = key.get('remoteJid', '')
        phone = ''.join(filter(str.isdigit, remote_jid.split('@')[0]))
        msg = data.get('message', {})
        text = (
            msg.get('conversation')
            or msg.get('extendedTextMessage', {}).get('text', '')
            or data.get('body', '')
        )
        is_group = remote_jid.endswith('@g.us')
        return phone, text, from_me, is_group

    # Formato free.uazapi.com (messageSenderPhone + message.text na raiz)
    # Estrutura: {"BaseUrl":..., "EventType":"messages", "messageSenderPhone":"556...",
    #             "message":{"text":"...", "fromMe":false, ...}, "chat":{...}}
    msg_data = body.get('message', {})
    from_me = msg_data.get('fromMe', body.get('fromMe', False))

    # Detecta se a mensagem vem de grupo
    is_group = bool(msg_data.get('isGroup', False))

    # Se é mensagem enviada por nós mesmos, ignorar imediatamente
    if from_me:
        return '', '', True, is_group

    chat_data = body.get('chat', {})
    # Extrai o número do remetente — tenta todos os campos possíveis do free.uazapi.com
    # msg_data.sender_pn = número puro | msg_data.sender = JID completo (ex: 556199...@s.whatsapp.net)
    # msg_data.chatid = JID do chat (ex: 556199...@s.whatsapp.net ou grupo@g.us)
    sender_raw = (
        body.get('messageSenderPhone')
        or msg_data.get('sender_pn')
        or msg_data.get('senderPhone')
        or msg_data.get('sender', '').split('@')[0]
        or chat_data.get('phone', '')
        or msg_data.get('chatid', '').split('@')[0]
    )
    phone = ''.join(filter(str.isdigit, sender_raw))

    # Tenta extrair texto em todos os campos possíveis
    text = (
        msg_data.get('text')
        or msg_data.get('body')
        or msg_data.get('conversation')
        or msg_data.get('extendedTextMessage', {}).get('text', '')
        or body.get('text')
        or body.get('body')
        or ''
    )

    if not phone or not text:
        logger.warning(
            f'Mensagem ignorada — phone={phone!r}, text={text!r}, '
            f'fromMe={from_me}, EventType={body.get("EventType")}, '
            f'msg_keys={list(msg_data.keys())}'
        )

    return phone, text, from_me, is_group


async def _handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """Lógica central do webhook — compartilhada entre rotas."""
    from app.config import settings

    try:
        body = await request.json()
    except Exception:
        return {'status': 'invalid_body'}

    phone, text, from_me, is_group = _parse_uazapi_body(body)

    if from_me:
        return {'status': 'ignored'}

    # Ignora mensagens de grupos — bot responde apenas em conversas diretas (DMs)
    if is_group:
        logger.debug(f'Mensagem de grupo ignorada: {text[:40]!r}')
        return {'status': 'ignored_group'}

    if not phone or not text:
        return {'status': 'ignored'}

    # Allowlist de números para testes controlados
    # Defina PHONE_ALLOWLIST=["5561..."] no Railway para limitar quem o bot responde
    if settings.PHONE_ALLOWLIST and phone not in settings.PHONE_ALLOWLIST:
        logger.info(f'Número {phone} fora da allowlist — ignorado')
        return {'status': 'not_in_allowlist'}

    logger.info(f'Mensagem recebida de {phone}: {text[:50]}')
    background_tasks.add_task(_process_message, phone, text)
    return {'status': 'processing'}


@router.post('')
async def webhook(request: Request, background_tasks: BackgroundTasks):
    return await _handle_webhook(request, background_tasks)


@router.post('/messages/{message_type}')
async def webhook_typed(message_type: str, request: Request, background_tasks: BackgroundTasks):
    return await _handle_webhook(request, background_tasks)
