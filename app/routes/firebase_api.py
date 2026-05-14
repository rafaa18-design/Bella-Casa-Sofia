"""Rotas internas da API Firebase — chamadas pelas tools da Sofia."""
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException
from google.cloud import firestore
from google.oauth2 import service_account
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/firebase', tags=['firebase'])

INTERNAL_TOKEN = os.getenv('FIREBASE_ADMIN_TOKEN', '')


def _check_token(authorization: str | None):
    if not authorization or authorization != f'Bearer {INTERNAL_TOKEN}':
        raise HTTPException(status_code=401, detail='Unauthorized')


def _get_db():
    credentials = service_account.Credentials.from_service_account_info({
        'type': 'service_account',
        'project_id': os.getenv('FIREBASE_ADMIN_PROJECT_ID'),
        'private_key': os.getenv('FIREBASE_ADMIN_PRIVATE_KEY', '').replace('\\n', '\n'),
        'client_email': os.getenv('FIREBASE_ADMIN_CLIENT_EMAIL'),
        'token_uri': 'https://oauth2.googleapis.com/token',
    })
    return firestore.Client(
        project=os.getenv('FIREBASE_ADMIN_PROJECT_ID'),
        credentials=credentials,
    )


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
async def get_lead_by_phone(
    phone: str,
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    db = _get_db()
    docs = db.collection('leads').where('phone', '==', phone).limit(1).stream()
    for doc in docs:
        data = doc.to_dict()
        seller_doc = db.collection('sellers').document(data.get('assignedSeller', '')).get()
        seller_name = seller_doc.to_dict().get('name', '') if seller_doc.exists else ''
        return {**data, 'id': doc.id, 'sellerName': seller_name}
    raise HTTPException(status_code=404, detail='Lead not found')


@router.post('/leads')
async def create_lead(
    payload: LeadPayload,
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    db = _get_db()
    now = datetime.utcnow()
    data = payload.model_dump()
    data['createdAt'] = now
    data['updatedAt'] = now
    ref = db.collection('leads').add(data)
    return {'id': ref[1].id}


@router.post('/leads/{lead_id}/assign')
async def assign_lead(
    lead_id: str,
    payload: AssignPayload,
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    db = _get_db()

    if payload.sellerId:
        seller_id = payload.sellerId
    else:
        # Round-robin
        control_ref = db.collection('roundRobin').document('control')
        control = control_ref.get().to_dict()
        sellers = control['sellers']
        idx = control['currentIndex']
        seller_id = sellers[idx]
        next_idx = (idx + 1) % len(sellers)
        control_ref.update({'currentIndex': next_idx})
        seller_ref = db.collection('sellers').document(seller_id)
        seller_doc = seller_ref.get().to_dict()
        seller_ref.update({'totalLeadsAssigned': seller_doc.get('totalLeadsAssigned', 0) + 1})

    db.collection('leads').document(lead_id).update({
        'assignedSeller': seller_id,
        'updatedAt': datetime.utcnow(),
    })

    seller = db.collection('sellers').document(seller_id).get().to_dict()
    return {'sellerId': seller_id, 'sellerName': seller.get('name', '')}


@router.post('/leads/{lead_id}/schedule-visit')
async def schedule_visit(
    lead_id: str,
    payload: VisitPayload,
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    db = _get_db()
    from datetime import timedelta, timezone as tz

    visit_dt = datetime.strptime(f"{payload.visitDate} {payload.visitTime}", '%d/%m/%Y %H:%M')
    logger.info(f"schedule_visit: lead={lead_id} date={payload.visitDate} time={payload.visitTime}")

    # Verifica conflitos com intervalo de 30 minutos (exclui o próprio lead no reagendamento)
    try:
        day_start = visit_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = visit_dt.replace(hour=23, minute=59, second=59)
        existing = db.collection('leads').where('visitDate', '>=', day_start).where('visitDate', '<=', day_end).stream()
        for doc in existing:
            if doc.id == lead_id:
                continue  # Ignora o próprio lead no reagendamento
            data = doc.to_dict()
            existing_dt = data.get('visitDate')
            if existing_dt:
                if hasattr(existing_dt, 'tzinfo') and existing_dt.tzinfo is not None:
                    existing_dt = existing_dt.replace(tzinfo=None)
                diff = abs((visit_dt - existing_dt).total_seconds()) / 60
                if diff < 30:
                    conflict_time = existing_dt.strftime('%H:%M')
                    suggested = (visit_dt + timedelta(minutes=30)).strftime('%H:%M')
                    return {
                        'success': False,
                        'conflict_message': (
                            f'Já temos uma visita agendada próxima às {conflict_time}. '
                            f'O próximo horário disponível seria às {suggested}.'
                        )
                    }
    except Exception as e:
        logger.warning(f"schedule_visit: conflict check failed (skipping): {e}")

    reminder_dt = visit_dt.replace(hour=19, minute=0, second=0) - timedelta(days=1)

    db.collection('leads').document(lead_id).update({
        'status': 'agendado',
        'visitDate': visit_dt,
        'visitTime': payload.visitTime,
        'updatedAt': datetime.utcnow(),
    })

    # Atualiza reminder existente (reagendamento) ou cria novo
    existing_reminders = list(
        db.collection('reminders').where('leadId', '==', lead_id).stream()
    )
    reminder_data = {
        'leadId': lead_id,
        'phone': payload.phone,
        'leadName': payload.leadName,
        'visitDate': visit_dt,
        'reminderScheduledFor': reminder_dt,
        'sent': False,
    }
    if existing_reminders:
        existing_reminders[0].reference.update(reminder_data)
        logger.info(f"schedule_visit: reminder atualizado para lead={lead_id}")
    else:
        db.collection('reminders').add(reminder_data)
        logger.info(f"schedule_visit: reminder criado para lead={lead_id}")

    logger.info(f"schedule_visit: agendado com sucesso lead={lead_id}")
    return {'success': True}


# ---------------------------------------------------------------------------
# Sellers — cadastro e exclusão
# ---------------------------------------------------------------------------

_firebase_admin_app = None


def _get_admin_app():
    """Inicializa o Firebase Admin SDK (singleton)."""
    global _firebase_admin_app
    import firebase_admin
    from firebase_admin import credentials as fb_creds
    if _firebase_admin_app is None:
        cred = fb_creds.Certificate({
            'type': 'service_account',
            'project_id': os.getenv('FIREBASE_ADMIN_PROJECT_ID'),
            'private_key': os.getenv('FIREBASE_ADMIN_PRIVATE_KEY', '').replace('\\n', '\n'),
            'client_email': os.getenv('FIREBASE_ADMIN_CLIENT_EMAIL'),
            'token_uri': 'https://oauth2.googleapis.com/token',
        })
        try:
            _firebase_admin_app = firebase_admin.get_app('sellers')
        except ValueError:
            _firebase_admin_app = firebase_admin.initialize_app(cred, name='sellers')
    return _firebase_admin_app


class SellerPayload(BaseModel):
    name: str
    email: str
    whatsappNumber: str


@router.post('/sellers')
async def create_seller(
    payload: SellerPayload,
    authorization: str | None = Header(default=None),
):
    """Cadastra nova vendedora: cria no Firebase Auth, Firestore e round-robin."""
    _check_token(authorization)
    from firebase_admin import auth as fb_auth
    import secrets

    app = _get_admin_app()
    db = _get_db()

    # 1. Cria usuário no Firebase Auth com senha temporária
    temp_password = secrets.token_urlsafe(12)
    try:
        user = fb_auth.create_user(
            email=payload.email,
            display_name=payload.name,
            password=temp_password,
            app=app,
        )
    except fb_auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=409, detail='E-mail já cadastrado no Firebase Auth.')
    except Exception as e:
        logger.error(f'create_seller: erro ao criar usuário no Auth: {e}')
        raise HTTPException(status_code=500, detail=f'Erro ao criar usuário: {e}')

    # 2. Gera link de redefinição de senha para a vendedora
    try:
        reset_link = fb_auth.generate_password_reset_link(payload.email, app=app)
    except Exception:
        reset_link = ''

    # 3. Cria documento no Firestore
    now = datetime.utcnow()
    seller_data = {
        'name': payload.name,
        'email': payload.email,
        'whatsappNumber': payload.whatsappNumber,
        'isActive': True,
        'totalLeadsAssigned': 0,
        'createdAt': now,
    }
    seller_ref = db.collection('sellers').document(user.uid)
    seller_ref.set(seller_data)

    # 4. Adiciona ao round-robin
    try:
        control_ref = db.collection('roundRobin').document('control')
        control = control_ref.get()
        if control.exists:
            current = control.to_dict().get('sellers', [])
            if user.uid not in current:
                control_ref.update({'sellers': current + [user.uid]})
        else:
            control_ref.set({'sellers': [user.uid], 'currentIndex': 0})
    except Exception as e:
        logger.warning(f'create_seller: erro ao atualizar round-robin: {e}')

    logger.info(f'create_seller: vendedora criada uid={user.uid} email={payload.email}')
    return {
        'id': user.uid,
        'name': payload.name,
        'email': payload.email,
        'resetLink': reset_link,
    }


@router.delete('/sellers/{seller_id}')
async def delete_seller(
    seller_id: str,
    authorization: str | None = Header(default=None),
):
    """Exclui vendedora do Firebase Auth, Firestore e round-robin."""
    _check_token(authorization)
    from firebase_admin import auth as fb_auth

    app = _get_admin_app()
    db = _get_db()

    # 1. Remove do Firebase Auth
    try:
        fb_auth.delete_user(seller_id, app=app)
    except fb_auth.UserNotFoundError:
        logger.warning(f'delete_seller: usuário {seller_id} não encontrado no Auth (continuando)')
    except Exception as e:
        logger.error(f'delete_seller: erro ao remover do Auth: {e}')
        raise HTTPException(status_code=500, detail=f'Erro ao remover usuário: {e}')

    # 2. Remove do Firestore
    db.collection('sellers').document(seller_id).delete()

    # 3. Remove do round-robin
    try:
        control_ref = db.collection('roundRobin').document('control')
        control = control_ref.get()
        if control.exists:
            sellers = control.to_dict().get('sellers', [])
            if seller_id in sellers:
                sellers.remove(seller_id)
                new_idx = min(control.to_dict().get('currentIndex', 0), max(len(sellers) - 1, 0))
                control_ref.update({'sellers': sellers, 'currentIndex': new_idx})
    except Exception as e:
        logger.warning(f'delete_seller: erro ao atualizar round-robin: {e}')

    logger.info(f'delete_seller: vendedora removida uid={seller_id}')
    return {'success': True}


# ---------------------------------------------------------------------------
# Conversations — chamado internamente pelo webhook
# ---------------------------------------------------------------------------

async def load_conversation_history(phone: str, limit: int = 20) -> list[dict]:
    """Carrega o histórico de conversa do Firestore para reconstruir contexto após reinício."""
    try:
        db = _get_db()
        docs = list(
            db.collection('conversations').where('phone', '==', phone).limit(1).stream()
        )
        if not docs:
            return []
        messages = docs[0].to_dict().get('messages', [])
        return [
            {'role': msg['role'], 'content': msg['content']}
            for msg in messages[-limit:]
        ]
    except Exception as e:
        logger.error(f'Erro ao carregar histórico do Firestore: {e}')
        return []


async def save_conversation_message(
    phone: str,
    lead_id: str,
    user_message: str,
    assistant_message: str,
    stage: str = 'qualificacao',
) -> None:
    """Salva as mensagens da conversa no Firestore (chamado pelo webhook)."""
    try:
        db = _get_db()
        now = datetime.utcnow()
        messages_to_add = [
            {'role': 'user', 'content': user_message, 'timestamp': now},
            {'role': 'assistant', 'content': assistant_message, 'timestamp': now},
        ]

        docs = list(
            db.collection('conversations').where('phone', '==', phone).limit(1).stream()
        )

        if docs:
            current_stage = docs[0].to_dict().get('stage', 'qualificacao')
            # Stage nunca regride: se já está encerrado, não volta para qualificacao
            final_stage = 'encerrado' if (stage == 'encerrado' or current_stage == 'encerrado') else stage
            update_data: dict = {
                'messages': firestore.ArrayUnion(messages_to_add),
                'stage': final_stage,
                'updatedAt': now,
            }
            if lead_id:
                update_data['leadId'] = lead_id
            db.collection('conversations').document(docs[0].id).update(update_data)
        else:
            db.collection('conversations').add({
                'phone': phone,
                'leadId': lead_id,
                'messages': messages_to_add,
                'stage': stage,
                'updatedAt': now,
            })
    except Exception as e:
        logger.error(f'Erro ao salvar conversa no Firestore: {e}')
