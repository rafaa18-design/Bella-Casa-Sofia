"""Langfuse client for prompt management.

Provides the Langfuse SDK client used by prompt_manager.py to fetch
versioned prompts. Tracing/observability is handled entirely by
OpenInference AgnoInstrumentor (see tracing.py).
"""

import logging

from langfuse import Langfuse

from app.config import settings

logger = logging.getLogger(__name__)

_langfuse: Langfuse | None = None


def get_langfuse() -> Langfuse | None:
    """Get the Langfuse client instance.

    Returns None if Langfuse is not configured or disabled.
    """
    global _langfuse

    if not settings.LANGFUSE_ENABLED:
        return None

    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        logger.warning('Langfuse credentials not configured')
        return None

    if _langfuse is None:
        try:
            _langfuse = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                host=settings.LANGFUSE_BASE_URL,
            )
            if _langfuse.auth_check():
                logger.info('Langfuse client authenticated successfully')
            else:
                logger.error('Langfuse authentication failed')
                _langfuse = None
        except Exception as e:
            logger.error(f'Failed to initialize Langfuse: {e}')
            _langfuse = None

    return _langfuse


def shutdown():
    """Shutdown the Langfuse client gracefully."""
    global _langfuse
    if _langfuse:
        try:
            _langfuse.flush()
            _langfuse.shutdown()
        except Exception as e:
            logger.error(f'Error shutting down Langfuse: {e}')
        finally:
            _langfuse = None
