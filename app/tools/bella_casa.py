"""Tools da Valentina — Bella Casa."""
import json
import logging
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from app.runtime import RunContext, StopAgentRun, tool

logger = logging.getLogger(__name__)

_port = os.getenv("PORT", "8000")
FIREBASE_URL = os.getenv("FIREBASE_BASE_URL") or f"http://localhost:{_port}/api/firebase"
FIREBASE_TOKEN = os.getenv("FIREBASE_ADMIN_TOKEN", "")

BAHIA_TZ = ZoneInfo("America/Bahia")

BUSINESS_HOURS = {
    0: ("08:00", "18:00"),  # Segunda
    1: ("08:00", "18:00"),  # Terça
    2: ("08:00", "18:00"),  # Quarta
    3: ("08:00", "18:00"),  # Quinta
    4: ("08:00", "18:00"),  # Sexta
    5: ("08:30", "13:00"),  # Sábado
    6: None,                # Domingo — fechado
}

DAY_NAMES = {
    0: "segunda-feira",
    1: "terça-feira",
    2: "quarta-feira",
    3: "quinta-feira",
    4: "sexta-feira",
    5: "sábado",
    6: "domingo",
}

MATRIZ_CITIES = {
    "santo antonio de jesus", "saj",
    "conceição do almeida", "conceicao do almeida",
    "dom macedo costa",
    "muniz ferreira",
    "aratuípe", "aratuipe",
    "laje",
    "são miguel das matas", "sao miguel das matas",
    "varzedo",
    "são felipe", "sao felipe",
    "nazaré", "nazare",
    "cruz das almas",
}


def _headers() -> dict:
    return {"Authorization": f"Bearer {FIREBASE_TOKEN}", "Content-Type": "application/json"}


@tool
async def verificar_cliente(run_context: RunContext) -> str:
    """Verifica se o cliente já possui cadastro (cliente recorrente).

    O telefone é obtido automaticamente do contexto da sessão.
    Retorna JSON com: is_recurring (bool), lead_id, assigned_seller, seller_name.
    Se não encontrado, retorna is_recurring: false.
    """
    phone = run_context.session_state.get("phone", "")
    if not phone:
        return '{"is_recurring": false}'

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{FIREBASE_URL}/leads/by-phone/{phone}",
                headers=_headers(),
                timeout=5,
            )
    except Exception as e:
        logger.error(f"verificar_cliente HTTP error: {e}")
        return '{"is_recurring": false}'

    if resp.status_code == 404:
        return '{"is_recurring": false}'

    if resp.status_code != 200:
        logger.error(f"verificar_cliente status {resp.status_code}: {resp.text[:200]}")
        return '{"is_recurring": false}'

    data = resp.json()
    run_context.session_state["lead_id"] = data.get("id")
    run_context.session_state["assigned_seller"] = data.get("assignedSeller")
    run_context.session_state["is_recurring"] = True
    return (
        f'{{"is_recurring": true, "lead_id": "{data.get("id")}", '
        f'"assigned_seller": "{data.get("assignedSeller")}", '
        f'"seller_name": "{data.get("sellerName", "")}", '
        f'"client_name": "{data.get("name", "")}"}}'
    )


@tool
def rotear_cidade(run_context: RunContext, city: str) -> str:
    """Define se o cliente é da praça da matriz ou de outra cidade (atendimento remoto).

    Retorna: routing_type ('matriz' ou 'remoto') e invite_visit (true se for matriz).
    Se invite_visit for true, você DEVE imediatamente convidar o cliente para visitar a loja.
    """
    normalized = city.lower().strip()
    routing = "matriz" if normalized in MATRIZ_CITIES else "remoto"
    invite_visit = routing == "matriz"
    run_context.session_state["routing_type"] = routing
    run_context.session_state["city"] = city
    return f'{{"routing_type": "{routing}", "city": "{city}", "invite_visit": {str(invite_visit).lower()}}}'


@tool
def verificar_horario(run_context: RunContext) -> str:
    """Verifica se o atendimento está dentro do horário comercial da Bella Casa.

    Retorna: is_open (bool), current_time, next_opening (se fechado).
    """
    now = datetime.now(BAHIA_TZ)
    weekday = now.weekday()
    current_time = now.strftime("%H:%M")
    hours = BUSINESS_HOURS.get(weekday)

    if hours is None:
        # Domingo — próxima abertura é segunda às 08h
        next_day = (weekday + 1) % 7
        while BUSINESS_HOURS.get(next_day) is None:
            next_day = (next_day + 1) % 7
        next_open, _ = BUSINESS_HOURS[next_day]
        return (
            f'{{"is_open": false, "current_time": "{current_time}", '
            f'"reason": "Fechado aos domingos", '
            f'"next_opening": "{DAY_NAMES[next_day]} às {next_open}"}}'
        )

    open_time, close_time = hours
    is_open = open_time <= current_time <= close_time

    if is_open:
        return f'{{"is_open": true, "current_time": "{current_time}"}}'

    # Fora do horário — calcular próxima abertura
    if current_time < open_time:
        next_opening = f"hoje às {open_time}"
    else:
        next_day = (weekday + 1) % 7
        while BUSINESS_HOURS.get(next_day) is None:
            next_day = (next_day + 1) % 7
        next_open, _ = BUSINESS_HOURS[next_day]
        next_opening = f"{DAY_NAMES[next_day]} às {next_open}"

    return (
        f'{{"is_open": false, "current_time": "{current_time}", '
        f'"next_opening": "{next_opening}"}}'
    )


@tool
async def registrar_lead(
    run_context: RunContext,
    name: str,
    city: str,
    product: str,
    purchase_timeline: str,
    purchase_purpose: str,
    language: str = "pt",
    ambient_size: str = "",
) -> str:
    """Registra o lead qualificado no banco de dados.

    O telefone do cliente é obtido automaticamente do contexto da conversa.

    Args:
        name: Nome do cliente.
        city: Cidade do cliente.
        product: Produto desejado com detalhes.
        purchase_timeline: 'imediato', '30_dias' ou 'pesquisando'.
        purchase_purpose: 'casa_nova', 'reforma' ou 'troca'.
        language: Idioma da conversa (pt, en, es).
        ambient_size: Metragem do ambiente (opcional).
    """
    phone = run_context.session_state.get("phone", "")
    # Se rotear_cidade não foi chamada, determina o routing pela cidade agora
    routing_type = run_context.session_state.get("routing_type", "")
    if not routing_type:
        routing_type = "matriz" if city.lower().strip() in MATRIZ_CITIES else "remoto"
        run_context.session_state["routing_type"] = routing_type

    payload = {
        "phone": phone,
        "name": name,
        "city": city,
        "routingType": routing_type,
        "product": product,
        "purchaseTimeline": purchase_timeline,
        "purchasePurpose": purchase_purpose,
        "language": language,
        "ambientSize": ambient_size,
        "isRecurring": False,
        "status": "novo",
        "visitReminderSent": False,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FIREBASE_URL}/leads",
                json=payload,
                headers=_headers(),
                timeout=10,
            )
    except Exception as e:
        logger.error(f"registrar_lead HTTP error: {e}")
        return f'{{"success": false, "error": "Falha ao conectar com o servidor: {e}"}}'

    if resp.status_code not in (200, 201):
        logger.error(f"registrar_lead status {resp.status_code}: {resp.text[:300]}")
        return f'{{"success": false, "error": "HTTP {resp.status_code}: {resp.text[:200]}"}}'

    data = resp.json()
    lead_id = data.get("id", "")
    if not lead_id:
        logger.error(f"registrar_lead: lead_id vazio na resposta: {data}")
        return '{"success": false, "error": "lead_id vazio na resposta do servidor"}'

    run_context.session_state["lead_id"] = lead_id
    run_context.session_state["lead_name"] = name
    logger.info(f"registrar_lead: lead criado com sucesso, id={lead_id}")
    return f'{{"success": true, "lead_id": "{lead_id}"}}'


@tool
async def distribuir_vendedora(
    run_context: RunContext,
    seller_id: str = "",
) -> str:
    """Atribui o lead a uma vendedora.

    Se seller_id for informado, reatribui ao seller específico (cliente recorrente).
    Se não, usa o round-robin automático.
    """
    lead_id = run_context.session_state.get("lead_id", "")
    phone = run_context.session_state.get("phone", "")

    if not lead_id and phone:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{FIREBASE_URL}/leads/by-phone/{phone}",
                    headers=_headers(),
                    timeout=5,
                )
            if r.status_code == 200:
                lead_id = r.json().get("id", "")
                run_context.session_state["lead_id"] = lead_id
        except Exception as e:
            logger.error(f"distribuir_vendedora: falha ao buscar lead_id: {e}")

    if not lead_id:
        return '{"success": false, "error": "lead_id não encontrado"}'

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FIREBASE_URL}/leads/{lead_id}/assign",
                json={"sellerId": seller_id or None},
                headers=_headers(),
                timeout=5,
            )
    except Exception as e:
        logger.error(f"distribuir_vendedora HTTP error: {e}")
        return '{"success": true, "seller_name": "nossa equipe"}'

    data = resp.json()
    seller_name = data.get("sellerName", "nossa equipe")
    run_context.session_state["assigned_seller_name"] = seller_name
    return f'{{"success": true, "seller_name": "{seller_name}"}}'


@tool
async def agendar_visita(
    run_context: RunContext,
    visit_date: str,
    visit_time: str,
) -> str:
    """Registra a data e horário de visita do cliente à loja e cria o lembrete automático.

    Valida se o horário está dentro do funcionamento da loja e verifica conflitos de agenda
    (intervalo mínimo de 30 minutos entre visitas).

    Args:
        visit_date: Data da visita no formato DD/MM/AAAA.
        visit_time: Horário da visita no formato HH:MM (ex: 09:00, 14:30).
    """
    from datetime import datetime as dt, timedelta

    now = dt.now(BAHIA_TZ)
    current_year = now.year

    # Mapeamento de nomes de dias da semana em português
    WEEKDAY_PT = {
        "segunda": 0, "segunda-feira": 0,
        "terca": 1, "terça": 1, "terca-feira": 1, "terça-feira": 1,
        "quarta": 2, "quarta-feira": 2,
        "quinta": 3, "quinta-feira": 3,
        "sexta": 4, "sexta-feira": 4,
        "sabado": 5, "sábado": 5, "sabado-feira": 5,
    }

    normalized_input = visit_date.lower().strip()
    date_with_year = None

    # Tenta identificar dia da semana
    for name, wday in WEEKDAY_PT.items():
        if name in normalized_input:
            days_ahead = (wday - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Próxima semana se for hoje
            target = now + timedelta(days=days_ahead)
            date_with_year = f"{str(target.day).zfill(2)}/{str(target.month).zfill(2)}/{current_year}"
            break

    # Se não encontrou dia da semana, extrai DD/MM numericamente
    if not date_with_year:
        date_match = re.search(r'(\d{1,2})[/\-\.](\d{1,2})', visit_date)
        if not date_match:
            return '{"success": false, "error": "Não consegui entender a data. Informe DD/MM ou o dia da semana (ex: segunda, terça)."}'
        day = date_match.group(1).zfill(2)
        month = date_match.group(2).zfill(2)
        date_with_year = f"{day}/{month}/{current_year}"

    # Extrai hora e minuto de qualquer string (ex: "11:00", "11h00", "11h")
    time_match = re.search(r'(\d{1,2})[:\-h](\d{2})?', visit_time)
    if not time_match:
        return '{"success": false, "error": "Não consegui entender o horário. Me informe no formato HH:MM (ex: 10:00)."}'
    hour = time_match.group(1).zfill(2)
    minute = (time_match.group(2) or "00").zfill(2)
    clean_time = f"{hour}:{minute}"

    try:
        visit_dt = dt.strptime(f"{date_with_year} {clean_time}", "%d/%m/%Y %H:%M")
    except ValueError:
        return '{"success": false, "error": "Data ou horário inválido. Use DD/MM para data e HH:MM para horário."}'

    # Verifica se é domingo (fechado)
    weekday = visit_dt.weekday()
    if weekday == 6:
        return '{"success": false, "error": "A loja não abre aos domingos. Escolha de segunda a sábado."}'

    # Valida horário comercial
    hours = BUSINESS_HOURS.get(weekday)
    if hours is None:
        return '{"success": false, "error": "Loja fechada neste dia."}'

    open_time, close_time = hours
    if not (open_time <= clean_time <= close_time):
        return (
            f'{{"success": false, "error": "Horário fora do funcionamento. '
            f'Neste dia atendemos das {open_time} às {close_time}."}}'
        )

    lead_id = run_context.session_state.get("lead_id", "")
    phone = run_context.session_state.get("phone", "")
    name = run_context.session_state.get("lead_name", "")

    # Se lead_id não está na sessão (nova mensagem), busca pelo telefone
    if not lead_id and phone:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{FIREBASE_URL}/leads/by-phone/{phone}",
                    headers=_headers(),
                    timeout=5,
                )
            if r.status_code == 200:
                lead_data = r.json()
                lead_id = lead_data.get("id", "")
                run_context.session_state["lead_id"] = lead_id
                if not name:
                    name = lead_data.get("name", "")
                    run_context.session_state["lead_name"] = name
        except Exception as e:
            logger.error(f"agendar_visita: falha ao buscar lead_id: {e}")

    if not lead_id:
        return '{"success": false, "error": "Cadastro não encontrado. Por favor, finalize o cadastro antes de agendar."}'

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FIREBASE_URL}/leads/{lead_id}/schedule-visit",
                json={"visitDate": date_with_year, "visitTime": clean_time, "phone": phone, "leadName": name},
                headers=_headers(),
                timeout=5,
            )
    except Exception as e:
        logger.error(f"agendar_visita HTTP error: {e}")
        return '{"success": false, "error": "Erro ao conectar com o servidor."}'

    if resp.status_code != 200:
        logger.error(f"agendar_visita status {resp.status_code}: {resp.text[:200]}")
        return f'{{"success": false, "error": "{resp.json().get("detail", "Erro ao agendar")}"}}'

    data = resp.json()
    if not data.get("success"):
        conflict_msg = data.get("conflict_message", "Horário indisponível.")
        return f'{{"success": false, "error": "{conflict_msg}"}}'

    run_context.session_state["visit_confirmed_date"] = date_with_year
    run_context.session_state["visit_confirmed_time"] = clean_time
    return '{"success": true, "reminder_scheduled": true}'


@tool
def transferir_vendedora(run_context: RunContext) -> str:
    """Finaliza o atendimento da Sofia, envia despedida ao cliente e sinaliza o handoff para a vendedora humana.

    Deve ser chamada SEMPRE ao final da qualificação ou ao identificar cliente recorrente.
    """
    seller_name = run_context.session_state.get("assigned_seller_name", "nossa equipe")
    lead_name = run_context.session_state.get("lead_name", "")
    routing_type = run_context.session_state.get("routing_type", "remoto")
    is_open = run_context.session_state.get("is_open", True)

    run_context.session_state["handoff_complete"] = True

    first_name = lead_name.split()[0] if lead_name else ""
    name_part = f"{first_name}, " if first_name else ""
    visit_date = run_context.session_state.get("visit_confirmed_date", "")
    visit_time = run_context.session_state.get("visit_confirmed_time", "")

    if visit_date and visit_time:
        farewell = (
            f"{name_part}sua visita esta confirmada para o dia {visit_date} as {visit_time}. "
            f"A {seller_name} vai te aguardar na loja. Ate logo!"
        )
    else:
        farewell = (
            f"{name_part}obrigada pelo contato com a Bella Casa! "
            f"A {seller_name} vai assumir seu atendimento agora e te ajudar com tudo que precisar. "
            f"Ate logo!"
        )
    run_context.session_state["farewell_message"] = farewell

    raise StopAgentRun(json.dumps({
        "handoff": True,
        "seller_name": seller_name,
        "lead_name": lead_name,
        "routing_type": routing_type,
        "within_business_hours": is_open,
        "farewell": farewell,
    }))
