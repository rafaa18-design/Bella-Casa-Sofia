"""Webhook do UazAPI — entrada de mensagens do WhatsApp para a Valentina."""
import logging
import os

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

    # Salva histórico em memória (últimas 20 mensagens)
    history.append({'role': 'user', 'content': text})
    history.append({'role': 'assistant', 'content': response.content})
    _history[phone] = history[-20:]

    # Determina estágio e persiste conversa no Firestore
    handoff_complete = run_context.session_state.get('handoff_complete', False)
    stage = 'encerrado' if handoff_complete else 'qualificacao'
    lead_id = run_context.session_state.get('lead_id', '')
    await save_conversation_message(phone, lead_id, text, response.content, stage)

    # Se handoff completo, limpa histórico em memória para próxima conversa
    if handoff_complete:
        _history.pop(phone, None)

    if response.content:
        await _send_whatsapp(phone, response.content)


@router.post('')
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Recebe mensagens do UazAPI e processa em background."""
    try:
        body = await request.json()
    except Exception:
        return {'status': 'invalid_body'}

    # Valida token da instância UazAPI (vem dentro do body)
    msg_data = body.get('message', {})
    incoming_token = msg_data.get('token', '')
    if UAZAPI_TOKEN and incoming_token and incoming_token != UAZAPI_TOKEN:
        logger.warning('Webhook recusado — token inválido')
        return {'status': 'unauthorized'}

    # Ignora mensagens enviadas pelo próprio número
    if msg_data.get('fromMe', False):
        return {'status': 'ignored'}

    phone = body.get('messageSenderPhone', '')
    text = body.get('text', '')
    msg_type = body.get('type', '')

    if not phone or not text or msg_type != 'text':
        return {'status': 'ignored'}

    logger.info(f'Mensagem recebida de {phone}: {text[:50]}')
    background_tasks.add_task(_process_message, phone, text)

    return {'status': 'processing'}
