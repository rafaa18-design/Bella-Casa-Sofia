"""Webhook do UazAPI — entrada de mensagens do WhatsApp para a Valentina."""
import logging
import os
import re

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
    """Envia mensagem de volta para o cliente via UazAPI."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f'{UAZAPI_URL}/message/text',
                headers={'token': UAZAPI_TOKEN},
                json={'phone': phone, 'message': text},
                timeout=10,
            )
    except Exception as e:
        logger.error(f'Erro ao enviar mensagem UazAPI: {e}')


async def _process_message(phone: str, text: str):
    """Processa a mensagem e gera resposta da Sofia."""
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
    message_to_send = '' if (handoff_complete and is_system_json) else raw_content

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

    if clean_content:
        await _send_whatsapp(phone, clean_content)


@router.post('')
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Recebe mensagens do UazAPI e processa em background."""
    try:
        body = await request.json()
    except Exception:
        return {'status': 'invalid_body'}

    # Campos da mensagem ficam dentro de body['message']
    msg_data = body.get('message', {})

    # Ignora mensagens enviadas pelo próprio número
    if msg_data.get('fromMe', False):
        return {'status': 'ignored'}

    # Tenta root primeiro, depois message, depois chat
    chat_data = body.get('chat', {})
    phone = (
        body.get('messageSenderPhone')
        or msg_data.get('senderPhone')
        or chat_data.get('phone', '')
    )
    # Remove caracteres não numéricos do telefone
    phone = ''.join(filter(str.isdigit, phone))
    text = body.get('text') or msg_data.get('text', '')
    msg_type = body.get('type') or msg_data.get('type', '')

    if not phone or not text or msg_type != 'text':
        return {'status': 'ignored'}

    logger.info(f'Mensagem recebida de {phone}: {text[:50]}')
    background_tasks.add_task(_process_message, phone, text)

    return {'status': 'processing'}
