"""Prompt management routes: /prompt/webhook, /prompt/refresh, /prompt/current."""

import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.observability import get_logger
from app.prompt_manager import get_prompt_manager

logger = get_logger(__name__)

prompt_router = APIRouter(prefix='/prompt', tags=['Prompt'])


@prompt_router.post('/webhook')
async def prompt_webhook(request: Request):
    """Receive webhooks from Langfuse with prompt updates."""
    try:
        raw_body = await request.body()
        raw_body_str = raw_body.decode('utf-8')

        signature_header = request.headers.get('x-langfuse-signature')

        if settings.LANGFUSE_SIGNATURE_SECRET:
            if not signature_header:
                raise HTTPException(
                    status_code=401, detail='Signature missing'
                )

            if not _verify_langfuse_signature(
                raw_body_str,
                signature_header,
                settings.LANGFUSE_SIGNATURE_SECRET,
            ):
                raise HTTPException(
                    status_code=401, detail='Invalid signature'
                )

        data = json.loads(raw_body_str)

        if not data or 'prompt' not in data or 'prompt' not in data['prompt']:
            raise HTTPException(
                status_code=400,
                detail='Field prompt.prompt not found in payload',
            )

        prompt_text = data['prompt']['prompt']
        logger.info(
            f'Langfuse webhook: received prompt with {len(prompt_text)} chars'
        )

        manager = get_prompt_manager()
        success = await manager.update_prompt_from_webhook(prompt_text)

        if success:
            return JSONResponse(
                content={'status': 'success', 'message': 'Prompt updated'},
                status_code=200,
            )
        else:
            return JSONResponse(
                content={
                    'status': 'ignored',
                    'message': 'Using versioned prompt',
                },
                status_code=200,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f'Langfuse webhook error: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@prompt_router.post('/refresh')
async def refresh_prompt():
    """Force refresh the prompt from Langfuse."""
    manager = get_prompt_manager()
    await manager.invalidate_cache()
    prompt = await manager.get_prompt()
    return {
        'status': 'success',
        'message': 'Prompt refreshed',
        'prompt_length': len(prompt),
    }


@prompt_router.post('/personalizacao')
async def set_personalizacao(request: Request):
    """Recebe personalização do gestor e armazena em memória."""
    try:
        data = await request.json()
        text = data.get('text', '')
        manager = get_prompt_manager()
        manager.set_personalizacao(text)
        return JSONResponse(content={'status': 'success', 'len': len(text)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@prompt_router.get('/debug-personalizacao')
async def debug_personalizacao():
    """Diagnóstico: verifica se a personalização está sendo lida do banco."""
    manager = get_prompt_manager()
    personalizacao = await manager._get_personalizacao()
    base = manager._fallback
    has_placeholder = '{{gestor_personalizacao}}' in base
    return {
        'personalizacao_text': personalizacao or '(vazio)',
        'personalizacao_len': len(personalizacao),
        'base_has_placeholder': has_placeholder,
        'base_len': len(base),
    }


@prompt_router.get('/current')
async def get_current_prompt():
    """Get the current prompt being used."""
    manager = get_prompt_manager()
    prompt = await manager.get_prompt()
    return {
        'prompt_length': len(prompt),
        'prompt_preview': prompt[:200] + '...'
        if len(prompt) > 200
        else prompt,
        'is_versioned': manager.is_versioned,
    }


def _verify_langfuse_signature(
    raw_body: str, signature_header: str, secret: str
) -> bool:
    """Validate Langfuse webhook signature."""
    try:
        ts_pair, sig_pair = signature_header.split(',', 1)
    except ValueError:
        return False

    if not ts_pair.startswith('t=') or not (
        sig_pair.startswith('s=') or sig_pair.startswith('v1=')
    ):
        return False

    timestamp = ts_pair.split('=', 1)[1]
    received_sig_hex = sig_pair.split('=', 1)[1]

    message = f'{timestamp}.{raw_body}'.encode('utf-8')
    expected_sig_hex = hmac.new(
        secret.encode('utf-8'), message, hashlib.sha256
    ).hexdigest()

    try:
        return hmac.compare_digest(
            bytes.fromhex(received_sig_hex), bytes.fromhex(expected_sig_hex)
        )
    except ValueError:
        return False
