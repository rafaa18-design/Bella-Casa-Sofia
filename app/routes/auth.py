"""Authentication routes: /auth/login, /auth/token."""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, HTTPException, Request

from app.auth import authenticate_user, get_scopes_from_token, has_required_scope
from app.config import settings
from app.observability import get_logger

logger = get_logger(__name__)

auth_router = APIRouter(prefix='/auth', tags=['Authentication'])


@auth_router.post('/login')
async def login(request: Request, username: str, password: str):
    """Login endpoint that returns JWT token."""
    from app.audit import audit_login_failure, audit_login_success

    client_ip = (
        request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    )
    if not client_ip and request.client:
        client_ip = request.client.host
    user_agent = request.headers.get('User-Agent')

    if not settings.JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail='JWT authentication not configured (set JWT_SECRET)',
        )

    if not settings.AUTH_USERS:
        raise HTTPException(
            status_code=500,
            detail='User authentication not configured (set AUTH_USERS)',
        )

    if not authenticate_user(username, password):
        logger.warning(f'Failed login attempt for user: {username}')
        audit_login_failure(
            username=username,
            reason='invalid_credentials',
            client_ip=client_ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=401, detail='Invalid credentials')

    now = datetime.now(UTC)
    payload = {
        'sub': username,
        'name': username,
        'iat': now,
        'exp': now + timedelta(hours=settings.JWT_EXPIRATION_HOURS),
        'scopes': ['agents:read', 'agents:run'],
    }

    token = jwt.encode(
        payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )

    logger.info(f'Successful login for user: {username}')
    audit_login_success(
        user_id=username,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return {
        'access_token': token,
        'token_type': 'bearer',
        'expires_in': settings.JWT_EXPIRATION_HOURS * 3600,
    }


@auth_router.post('/token')
async def create_token(
    request: Request,
    user_id: str,
    scopes: list[str] | None = None,
    expires_hours: int | None = None,
):
    """Create a JWT token programmatically (admin only)."""
    from app.audit import audit_auth_denied, audit_token_created

    if not settings.JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail='JWT authentication not configured',
        )

    # Verify caller has admin privileges
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPException(
            status_code=401,
            detail='Authentication required to create tokens',
        )

    try:
        token = auth_header.split(' ')[1]
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        caller_scopes = get_scopes_from_token(payload)
        caller_id = payload.get('sub')

        if not has_required_scope(caller_scopes, settings.AUTH_ADMIN_SCOPES):
            logger.warning(
                f'Token creation denied - user {caller_id} '
                f'lacks required scopes: {settings.AUTH_ADMIN_SCOPES}'
            )
            audit_auth_denied(
                user_id=caller_id,
                resource='/auth/token',
                reason=f'Missing required scopes: {settings.AUTH_ADMIN_SCOPES}',
            )
            raise HTTPException(
                status_code=403,
                detail=f'Requires one of: {settings.AUTH_ADMIN_SCOPES}',
            )
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f'Invalid token: {e}')

    now = datetime.now(UTC)
    exp_hours = expires_hours or settings.JWT_EXPIRATION_HOURS

    new_payload = {
        'sub': user_id,
        'iat': now,
        'exp': now + timedelta(hours=exp_hours),
        'scopes': scopes or ['agents:read', 'agents:run'],
        'created_by': caller_id,  # Track who created the token
    }

    new_token = jwt.encode(
        new_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )

    logger.info(f'Token created for user {user_id} by {caller_id}')
    audit_token_created(
        issuer_id=caller_id,
        target_user_id=user_id,
        scopes=scopes or ['agents:read', 'agents:run'],
        expires_in=exp_hours * 3600,
    )
    return {'access_token': new_token, 'token_type': 'bearer'}
