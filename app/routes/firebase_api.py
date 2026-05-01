"""Rotas internas da API Firebase — chamadas pelas tools da Valentina."""
import os
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException
from google.cloud import firestore
from google.oauth2 import service_account
from pydantic import BaseModel

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

    visit_dt = datetime.strptime(payload.visitDate, '%d/%m/%Y')
    reminder_dt = visit_dt.replace(hour=19, minute=0, second=0)
    from datetime import timedelta
    reminder_dt = reminder_dt - timedelta(days=1)

    db.collection('leads').document(lead_id).update({
        'status': 'agendado',
        'visitDate': visit_dt,
        'updatedAt': datetime.utcnow(),
    })

    db.collection('reminders').add({
        'leadId': lead_id,
        'phone': payload.phone,
        'leadName': payload.leadName,
        'visitDate': visit_dt,
        'reminderScheduledFor': reminder_dt,
        'sent': False,
    })

    return {'success': True}
