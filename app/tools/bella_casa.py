"""Tools da Valentina — Bella Casa."""
import logging
import os
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

    Retorna: routing_type ('matriz' ou 'remoto').
    """
    normalized = city.lower().strip()
    routing = "matriz" if normalized in MATRIZ_CITIES else "remoto"
    run_context.session_state["routing_type"] = routing
    run_context.session_state["city"] = city
    return f'{{"routing_type": "{routing}", "city": "{city}"}}'


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

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{FIREBASE_URL}/leads/{lead_id}/assign",
            json={"sellerId": seller_id or None},
            headers=_headers(),
            timeout=5,
        )

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
    from datetime import datetime as dt

    # Valida e parseia data + hora
    try:
        visit_dt = dt.strptime(f"{visit_date} {visit_time}", "%d/%m/%Y %H:%M")
    except ValueError:
        return '{"success": false, "error": "Formato inválido. Use DD/MM/AAAA para data e HH:MM para horário."}'

    # Verifica se é domingo (fechado)
    weekday = visit_dt.weekday()
    if weekday == 6:
        return '{"success": false, "error": "A loja não abre aos domingos. Escolha de segunda a sábado."}'

    # Valida horário comercial
    hours = BUSINESS_HOURS.get(weekday)
    if hours is None:
        return '{"success": false, "error": "Loja fechada neste dia."}'

    open_time, close_time = hours
    if not (open_time <= visit_time <= close_time):
        return (
            f'{{"success": false, "error": "Horário fora do funcionamento. '
            f'Neste dia atendemos das {open_time} às {close_time}."}}'
        )

    lead_id = run_context.session_state.get("lead_id", "")
    phone = run_context.session_state.get("phone", "")
    name = run_context.session_state.get("lead_name", "")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FIREBASE_URL}/leads/{lead_id}/schedule-visit",
                json={"visitDate": visit_date, "visitTime": visit_time, "phone": phone, "leadName": name},
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

    return '{"success": true, "reminder_scheduled": true}'


@tool
def transferir_vendedora(run_context: RunContext) -> str:
    """Finaliza o atendimento da Valentina e sinaliza o handoff para a vendedora humana.

    Deve ser chamada SEMPRE ao final da qualificação ou ao identificar cliente recorrente.
    """
    seller_name = run_context.session_state.get("assigned_seller_name", "nossa equipe")
    lead_name = run_context.session_state.get("lead_name", "")
    routing_type = run_context.session_state.get("routing_type", "remoto")
    is_open = run_context.session_state.get("is_open", True)

    run_context.session_state["handoff_complete"] = True

    raise StopAgentRun(
        f'{{"handoff": true, "seller_name": "{seller_name}", '
        f'"lead_name": "{lead_name}", "routing_type": "{routing_type}", '
        f'"within_business_hours": {str(is_open).lower()}}}'
    )
