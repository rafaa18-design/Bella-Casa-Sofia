"""Rotas internas /api/firebase/* — backend Postgres (substitui Firestore).

O prefixo /api/firebase foi mantido para não quebrar app/tools/bella_casa.py.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import (
    Conversation,
    Lead,
    Message,
    Reminder,
    RoundRobinControl,
    Seller,
    async_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/firebase', tags=['firebase'])

INTERNAL_TOKEN = os.getenv('FIREBASE_ADMIN_TOKEN', '')


def _check_token(authorization: str | None) -> None:
    if not authorization or authorization != f'Bearer {INTERNAL_TOKEN}':
        raise HTTPException(status_code=401, detail='Unauthorized')


def _timeline_to_db(v: str) -> str:
    return 'trinta_dias' if v == '30_dias' else v


def _timeline_from_db(v: str) -> str:
    return '30_dias' if v == 'trinta_dias' else v


def _lead_to_dict(lead: Lead, seller_name: str = '') -> dict:
    return {
        'id': lead.id,
        'phone': lead.phone,
        'name': lead.name,
        'city': lead.city,
        'routingType': lead.routing_type,
        'product': lead.product,
        'purchasePurpose': lead.purchase_purpose,
        'purchaseTimeline': _timeline_from_db(lead.purchase_timeline),
        'ambientSize': lead.ambient_size or '',
        'assignedSeller': lead.assigned_seller_id or '',
        'sellerName': seller_name,
        'isRecurring': lead.is_recurring,
        'status': lead.status,
        'visitDate': lead.visit_date.isoformat() if lead.visit_date else None,
        'visitReminderSent': lead.visit_reminder_sent,
        'createdAt': lead.created_at.isoformat(),
        'updatedAt': lead.updated_at.isoformat(),
        'language': lead.language,
    }


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


class LeadPayload(BaseModel):
    phone: str
    name: str
    city: str
    routingType: str
    product: str
    purchaseTimeline: str
    purchasePurpose: str
    language: str = 'pt'
    ambientSize: str = ''
    isRecurring: bool = False
    status: str = 'novo'
    visitReminderSent: bool = False


class AssignPayload(BaseModel):
    sellerId: str | None = None


class VisitPayload(BaseModel):
    visitDate: str
    visitTime: str
    phone: str
    leadName: str


@router.get('/leads/by-phone/{phone}')
async def get_lead_by_phone(phone: str, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    async with async_session() as s:
        stmt = select(Lead).where(Lead.phone == phone).limit(1)
        lead = (await s.execute(stmt)).scalar_one_or_none()
        if not lead:
            raise HTTPException(status_code=404, detail='Lead not found')
        seller_name = ''
        if lead.assigned_seller_id:
            seller = await s.get(Seller, lead.assigned_seller_id)
            seller_name = seller.name if seller else ''
        return _lead_to_dict(lead, seller_name)


@router.post('/leads')
async def create_lead(payload: LeadPayload, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    async with async_session() as s:
        lead = Lead(
            id=secrets.token_urlsafe(12),
            phone=payload.phone,
            name=payload.name,
            city=payload.city,
            routing_type=payload.routingType,
            product=payload.product,
            purchase_purpose=payload.purchasePurpose,
            purchase_timeline=_timeline_to_db(payload.purchaseTimeline),
            ambient_size=payload.ambientSize or None,
            is_recurring=payload.isRecurring,
            status=payload.status,
            visit_reminder_sent=payload.visitReminderSent,
            language=payload.language,
        )
        s.add(lead)
        await s.commit()
        return {'id': lead.id}


async def _next_seller_round_robin(s: AsyncSession) -> str:
    control = await s.get(RoundRobinControl, 'control')
    if control is None:
        control = RoundRobinControl(id='control', next_seller_idx=0, seller_order=[])
        s.add(control)
        await s.flush()

    order: list[str] = list(control.seller_order)
    if not order:
        active = await s.execute(
            select(Seller.id).where(Seller.is_active.is_(True)).order_by(Seller.created_at)
        )
        order = [r[0] for r in active.all()]
        if not order:
            raise HTTPException(status_code=409, detail='Nenhuma vendedora ativa cadastrada.')

    idx = control.next_seller_idx % len(order)
    assigned = order[idx]
    control.seller_order = order
    control.next_seller_idx = (idx + 1) % len(order)

    seller = await s.get(Seller, assigned)
    if seller:
        seller.total_leads_assigned += 1
    return assigned


@router.post('/leads/{lead_id}/assign')
async def assign_lead(
    lead_id: str,
    payload: AssignPayload,
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    async with async_session() as s:
        seller_id = payload.sellerId or await _next_seller_round_robin(s)

        lead = await s.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail='Lead not found')
        lead.assigned_seller_id = seller_id

        seller = await s.get(Seller, seller_id)
        await s.commit()
        return {'sellerId': seller_id, 'sellerName': seller.name if seller else ''}


@router.post('/leads/{lead_id}/schedule-visit')
async def schedule_visit(
    lead_id: str,
    payload: VisitPayload,
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    visit_dt = datetime.strptime(
        f'{payload.visitDate} {payload.visitTime}', '%d/%m/%Y %H:%M'
    ).replace(tzinfo=timezone.utc)
    logger.info('schedule_visit: lead=%s date=%s time=%s', lead_id, payload.visitDate, payload.visitTime)

    async with async_session() as s:
        # Conflito ±30min no mesmo dia (exclui o próprio lead)
        day_start = visit_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = visit_dt.replace(hour=23, minute=59, second=59)
        existing = await s.execute(
            select(Lead).where(
                Lead.visit_date >= day_start,
                Lead.visit_date <= day_end,
                Lead.id != lead_id,
            )
        )
        for other in existing.scalars():
            if other.visit_date is None:
                continue
            diff = abs((visit_dt - other.visit_date).total_seconds()) / 60
            if diff < 30:
                conflict_time = other.visit_date.strftime('%H:%M')
                suggested = (visit_dt + timedelta(minutes=30)).strftime('%H:%M')
                return {
                    'success': False,
                    'conflict_message': (
                        f'Já temos uma visita agendada próxima às {conflict_time}. '
                        f'O próximo horário disponível seria às {suggested}.'
                    ),
                }

        lead = await s.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail='Lead not found')
        lead.status = 'agendado'
        lead.visit_date = visit_dt

        reminder_dt = visit_dt.replace(hour=19, minute=0, second=0) - timedelta(days=1)
        existing_reminder = (
            await s.execute(select(Reminder).where(Reminder.lead_id == lead_id).limit(1))
        ).scalar_one_or_none()

        if existing_reminder:
            existing_reminder.phone = payload.phone
            existing_reminder.lead_name = payload.leadName
            existing_reminder.visit_date = visit_dt
            existing_reminder.reminder_scheduled_for = reminder_dt
            existing_reminder.sent = False
        else:
            s.add(
                Reminder(
                    id=secrets.token_urlsafe(12),
                    lead_id=lead_id,
                    phone=payload.phone,
                    lead_name=payload.leadName,
                    visit_date=visit_dt,
                    reminder_scheduled_for=reminder_dt,
                )
            )

        await s.commit()
        return {'success': True}


# ---------------------------------------------------------------------------
# Sellers
# ---------------------------------------------------------------------------


class SellerPayload(BaseModel):
    name: str
    email: str
    whatsappNumber: str


@router.post('/sellers')
async def create_seller(payload: SellerPayload, authorization: str | None = Header(default=None)):
    """Cadastra vendedora no Postgres com senha temporária bcrypt."""
    _check_token(authorization)
    email = payload.email.strip().lower()
    async with async_session() as s:
        existing = (
            await s.execute(select(Seller).where(Seller.email == email))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail='E-mail já cadastrado.')

        temp_password = secrets.token_urlsafe(9)
        password_hash = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt(12)).decode()
        seller = Seller(
            id=secrets.token_urlsafe(12),
            name=payload.name,
            email=email,
            password_hash=password_hash,
            whatsapp_number=payload.whatsappNumber,
            is_active=True,
            total_leads_assigned=0,
        )
        s.add(seller)

        control = await s.get(RoundRobinControl, 'control')
        if control is None:
            s.add(RoundRobinControl(id='control', next_seller_idx=0, seller_order=[seller.id]))
        else:
            order = list(control.seller_order)
            if seller.id not in order:
                order.append(seller.id)
                control.seller_order = order

        await s.commit()
        logger.info('create_seller: vendedora criada id=%s email=%s', seller.id, email)
        return {
            'id': seller.id,
            'name': seller.name,
            'email': seller.email,
            'tempPassword': temp_password,
        }


@router.delete('/sellers/{seller_id}')
async def delete_seller(seller_id: str, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    async with async_session() as s:
        seller = await s.get(Seller, seller_id)
        if not seller:
            raise HTTPException(status_code=404, detail='Seller not found')
        await s.delete(seller)

        control = await s.get(RoundRobinControl, 'control')
        if control is not None:
            order = [sid for sid in control.seller_order if sid != seller_id]
            control.seller_order = order
            control.next_seller_idx = (
                0 if control.next_seller_idx >= len(order) else control.next_seller_idx
            )

        await s.commit()
        logger.info('delete_seller: vendedora removida id=%s', seller_id)
        return {'success': True}


# ---------------------------------------------------------------------------
# Conversations — usados pelo webhook
# ---------------------------------------------------------------------------


async def load_conversation_history(phone: str, limit: int = 20) -> list[dict]:
    """Carrega histórico recente da conversa do Postgres."""
    try:
        async with async_session() as s:
            stmt = (
                select(Message)
                .join(Conversation, Conversation.lead_id == Message.lead_id)
                .where(Conversation.phone == phone)
                .order_by(Message.timestamp.desc())
                .limit(limit)
            )
            rows = list((await s.execute(stmt)).scalars())
            rows.reverse()
            return [{'role': m.role, 'content': m.content} for m in rows]
    except Exception as e:
        logger.error('Erro ao carregar histórico do Postgres: %s', e)
        return []


async def save_conversation_message(
    phone: str,
    lead_id: str,
    user_message: str,
    assistant_message: str,
    stage: str = 'qualificacao',
) -> None:
    """Persiste o par user/assistant. Stage nunca regride (encerrado é terminal)."""
    if not lead_id:
        logger.warning('save_conversation_message: lead_id vazio, ignorando')
        return
    try:
        async with async_session() as s:
            conv = await s.get(Conversation, lead_id)
            if conv is None:
                conv = Conversation(lead_id=lead_id, phone=phone, stage=stage)
                s.add(conv)
            else:
                final_stage = (
                    'encerrado' if stage == 'encerrado' or conv.stage == 'encerrado' else stage
                )
                conv.stage = final_stage

            now = datetime.now(timezone.utc)
            s.add(Message(lead_id=lead_id, role='user', content=user_message, timestamp=now))
            s.add(
                Message(lead_id=lead_id, role='assistant', content=assistant_message, timestamp=now)
            )
            await s.commit()
    except Exception as e:
        logger.error('Erro ao salvar conversa no Postgres: %s', e)
