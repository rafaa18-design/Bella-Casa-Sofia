"""Agendador de lembretes automáticos — visitas e follow-up de leads frios."""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def send_visit_reminders() -> None:
    """Envia lembretes de visita para clientes na véspera do agendamento."""
    from app.routes.firebase_api import _get_db
    from app.routes.webhook import _send_whatsapp

    logger.info('Scheduler: verificando lembretes de visita...')
    db  = _get_db()
    now = datetime.now(timezone.utc)

    try:
        # Busca apenas por sent=False e filtra reminderScheduledFor no Python
        # para evitar índice composto no Firestore
        docs = list(
            db.collection('reminders')
            .where('sent', '==', False)
            .stream()
        )

        if not docs:
            logger.info('Scheduler: nenhum lembrete de visita pendente.')
            return

        for doc in docs:
            data      = doc.to_dict()
            phone     = data.get('phone', '')
            lead_name = data.get('leadName', '')
            visit_dt  = data.get('visitDate')

            # Filtra por reminderScheduledFor <= now no Python
            reminder_time = data.get('reminderScheduledFor')
            if reminder_time:
                reminder_dt = reminder_time if hasattr(reminder_time, 'tzinfo') else reminder_time.replace(tzinfo=timezone.utc)
                if hasattr(reminder_dt, 'tzinfo') and reminder_dt.tzinfo is None:
                    reminder_dt = reminder_dt.replace(tzinfo=timezone.utc)
                if reminder_dt > now:
                    continue

            if not phone:
                continue

            first_name = lead_name.split()[0] if lead_name else ''
            greeting   = f'Ola, {first_name}!' if first_name else 'Ola!'

            visit_str = ''
            if visit_dt and hasattr(visit_dt, 'strftime'):
                visit_str = visit_dt.strftime('%d/%m/%Y as %H:%M')

            msg = (
                f'{greeting} Sofia da Bella Casa por aqui. '
                f'Passando para lembrar da sua visita a nossa loja amanha'
                f'{" (" + visit_str + ")" if visit_str else ""}. '
                f'Aguardamos voce na Av Urcisino Pinto de Queiroz, 68 - Santo Antonio de Jesus. '
                f'Caso precise reagendar, e so nos avisar!'
            )

            await _send_whatsapp(phone, msg)
            db.collection('reminders').document(doc.id).update({
                'sent':        True,
                'sentAt':      datetime.now(timezone.utc),
                'sentMessage': msg,
            })
            logger.info(f'Scheduler: lembrete de visita enviado para {phone}')

    except Exception as e:
        logger.error(f'Scheduler: erro ao enviar lembretes de visita: {e}')


async def send_cold_lead_followups() -> None:
    """Envia follow-up para leads novos sem resposta há 5+ dias e marca como frio."""
    from app.routes.firebase_api import _get_db
    from app.routes.webhook import _send_whatsapp

    logger.info('Scheduler: verificando leads frios...')
    db     = _get_db()
    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=5)

    try:
        # Busca por status e filtra por data no Python para evitar composite index
        docs = list(
            db.collection('leads')
            .where('status', '==', 'novo')
            .stream()
        )

        sent_count = 0

        for doc in docs:
            data       = doc.to_dict()
            phone      = data.get('phone', '')
            name       = data.get('name', '')
            product    = data.get('product', '')
            created_at = data.get('createdAt')

            if not phone or not created_at:
                continue

            # Normaliza e verifica se já passou dos 5 dias
            if hasattr(created_at, 'tzinfo') and created_at.tzinfo is not None:
                if created_at > cutoff:
                    continue
            else:
                cutoff_naive = cutoff.replace(tzinfo=None)
                if not isinstance(created_at, datetime) or created_at > cutoff_naive:
                    continue

            first_name  = name.split()[0] if name else ''
            greeting    = f'Ola, {first_name}!' if first_name else 'Ola!'
            product_str = product.split(',')[0].strip() if product else 'moveis'

            msg = (
                f'{greeting} Sofia da Bella Casa por aqui. '
                f'Vi que voce estava procurando {product_str} e queria saber se ainda posso te ajudar. '
                f'Estamos a disposicao quando quiser retomar!'
            )

            await _send_whatsapp(phone, msg)
            db.collection('leads').document(doc.id).update({
                'status':    'frio',
                'updatedAt': datetime.utcnow(),
            })
            logger.info(f'Scheduler: follow-up enviado para {phone} — lead marcado como frio')
            sent_count += 1

        logger.info(f'Scheduler: {sent_count} follow-up(s) de lead frio enviado(s).')

    except Exception as e:
        logger.error(f'Scheduler: erro ao enviar follow-ups: {e}')


def start_scheduler() -> None:
    """Inicia o agendador com os dois jobs.

    Horários em UTC (Bahia = UTC-3):
      - Lembretes de visita : 21h30 UTC = 18h30 BRT
      - Follow-up lead frio : 13h00 UTC = 10h00 BRT
    """
    scheduler.add_job(
        send_visit_reminders,
        trigger='cron',
        hour=21,
        minute=30,
        id='visit_reminders',
        replace_existing=True,
    )

    scheduler.add_job(
        send_cold_lead_followups,
        trigger='cron',
        hour=13,
        minute=0,
        id='cold_lead_followups',
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        'Agendador iniciado — '
        'lembretes de visita: 21h30 UTC (18h30 BRT) | '
        'follow-up frio: 13h00 UTC (10h00 BRT)'
    )


def stop_scheduler() -> None:
    """Para o agendador de forma segura."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info('Agendador encerrado.')
