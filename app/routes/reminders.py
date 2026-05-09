"""Endpoints de gerenciamento e teste dos lembretes automáticos."""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.scheduler import (
    scheduler,
    send_cold_lead_followups,
    send_visit_reminders,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/reminders', tags=['reminders'])


class JobStatus(BaseModel):
    id:       str
    next_run: str | None


@router.get('/status')
async def reminders_status():
    """Retorna o status do agendador e o próximo horário de cada job."""
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append(JobStatus(
            id=job.id,
            next_run=next_run.isoformat() if next_run else None,
        ))
    return {
        'running': scheduler.running,
        'jobs':    [j.model_dump() for j in jobs],
    }


@router.post('/trigger/visitas')
async def trigger_visit_reminders():
    """Dispara manualmente os lembretes de visita (para testes)."""
    logger.info('Trigger manual: lembretes de visita')
    await send_visit_reminders()
    return {'status': 'ok', 'message': 'Lembretes de visita processados.'}


@router.post('/trigger/frios')
async def trigger_cold_followups():
    """Dispara manualmente o follow-up de leads frios (para testes)."""
    logger.info('Trigger manual: follow-up de leads frios')
    await send_cold_lead_followups()
    return {'status': 'ok', 'message': 'Follow-up de leads frios processado.'}
