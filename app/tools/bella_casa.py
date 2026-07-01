"""Tools da Valentina — Bella Casa."""
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from app.runtime import RunContext, StopAgentRun, tool

logger = logging.getLogger(__name__)

_port = os.getenv("PORT", "8000")
FIREBASE_URL = os.getenv("FIREBASE_BASE_URL") or f"http://localhost:{_port}/api/firebase"
FIREBASE_TOKEN = os.getenv("FIREBASE_ADMIN_TOKEN", "")

# UazAPI (envio de mídia/foto ao cliente)
UAZAPI_URL = os.getenv("UAZAPI_URL", "")
UAZAPI_TOKEN = os.getenv("UAZAPI_TOKEN", "")
# URL pública do próprio agente (para o WhatsApp buscar a imagem). Ex: https://...onrender.com
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# Índice de fotos dos produtos (gerado por scripts/preparar_fotos.py)
_FOTOS_INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "fotos_index.json")


def _load_fotos_index() -> list[dict]:
    try:
        with open(_FOTOS_INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"fotos_index indisponível: {e}")
        return []


_FOTOS = _load_fotos_index()
logger.info(f"Fotos de produtos carregadas: {len(_FOTOS)}")


def _norm_foto(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# Palavras genéricas de categoria — não servem para achar um MODELO específico
_CAT_WORDS_FOTO = {
    "mesa", "mesas", "sofa", "sofas", "cadeira", "cadeiras", "poltrona", "poltronas",
    "aparador", "aparadores", "banco", "bancos", "bar", "bares", "buffet", "buffets",
    "espelho", "espelhos", "conjunto", "conjuntos", "puff", "puffs", "banqueta",
    "banquetas", "estante", "estantes", "castical", "lateral", "centro", "jantar",
}

# Palavras de preenchimento — ignoradas ao procurar um modelo específico
_STOPWORDS_FOTO = {
    "quero", "queria", "uma", "preciso", "gostaria", "procuro", "procurando",
    "tenho", "interesse", "voces", "vcs", "ver", "algum", "alguma", "modelo",
    "modelos", "opcao", "opcoes", "tipo", "sobre", "para", "com", "mais", "esse",
    "essa", "aqui", "isso", "queiro", "buscando", "busco", "gostei", "olha",
}


def _achar_foto(query: str) -> dict | None:
    """Encontra o produto fotografado que melhor casa com a busca (modelo ou categoria)."""
    q = _norm_foto(query)
    if not q or not _FOTOS:
        return None
    # 1) nome do produto contido na busca ou vice-versa (ex: "poltrona nuvem")
    for p in _FOTOS:
        n = _norm_foto(p["nome"])
        if n in q or q in n:
            return p
    # 2) token ESPECÍFICO (nome de modelo, não palavra de categoria) bate com o nome
    #    Ex: "mesa oslo" -> ignora "mesa", casa "oslo".
    tem_especifico = False
    for tok in q.split():
        if len(tok) < 4 or tok in _CAT_WORDS_FOTO or tok in _STOPWORDS_FOTO:
            continue
        tem_especifico = True
        for p in _FOTOS:
            if tok in _norm_foto(p["nome"]):
                return p
    # 3) categoria — só se o cliente NÃO citou um modelo específico que não temos.
    #    (Se pediu "mesa oslo" e não há Oslo, não mostramos outra mesa qualquer.)
    if not tem_especifico:
        for p in _FOTOS:
            if p.get("categoria") and p["categoria"] in q:
                return p
    return None


async def _send_media(number: str, file_url: str, caption: str = "") -> bool:
    """Envia uma imagem ao cliente via UazAPI (POST /send/media)."""
    token = UAZAPI_TOKEN.strip()
    base = UAZAPI_URL.strip().rstrip("/")
    if not base or not token:
        logger.error("UazAPI não configurado para envio de mídia")
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base}/send/media",
                headers={"token": token},
                json={"number": number, "type": "image", "file": file_url, "text": caption},
                timeout=20,
            )
        if resp.status_code not in (200, 201):
            logger.error(f"_send_media status {resp.status_code}: {resp.text[:200]}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"_send_media erro: {e}")
        return False

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
    hour = now.hour
    hours = BUSINESS_HOURS.get(weekday)

    if 5 <= hour < 12:
        saudacao = "Bom dia"
    elif 12 <= hour < 18:
        saudacao = "Boa tarde"
    else:
        saudacao = "Boa noite"

    if hours is None:
        next_day = (weekday + 1) % 7
        while BUSINESS_HOURS.get(next_day) is None:
            next_day = (next_day + 1) % 7
        next_open, _ = BUSINESS_HOURS[next_day]
        return (
            f'{{"is_open": false, "current_time": "{current_time}", '
            f'"saudacao": "{saudacao}", '
            f'"reason": "Fechado aos domingos", '
            f'"next_opening": "{DAY_NAMES[next_day]} às {next_open}"}}'
        )

    open_time, close_time = hours
    is_open = open_time <= current_time <= close_time

    if is_open:
        return f'{{"is_open": true, "current_time": "{current_time}", "saudacao": "{saudacao}"}}'

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
        f'"saudacao": "{saudacao}", '
        f'"next_opening": "{next_opening}"}}'
    )


@tool
async def registrar_lead(
    run_context: RunContext,
    name: str,
    product: str,
    city: str = "",
    purchase_timeline: str = "pesquisando",
    purchase_purpose: str = "casa_nova",
    language: str = "pt",
    ambient_size: str = "",
) -> str:
    """Registra o lead qualificado no banco de dados.

    O telefone do cliente é obtido automaticamente do contexto da conversa.
    Só name e product são obrigatórios. Cidade, prazo e finalidade são
    opcionais — preencha apenas se o cliente mencionar espontaneamente;
    caso contrário, deixe nos valores padrão.

    Args:
        name: Nome do cliente.
        product: Produto desejado com detalhes.
        city: Cidade do cliente (opcional; vazio se não informada).
        purchase_timeline: 'imediato', '30_dias' ou 'pesquisando' (padrão: pesquisando).
        purchase_purpose: 'casa_nova', 'reforma' ou 'troca' (padrão: casa_nova).
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
        return f'{{"success": false, "error": "Falha ao conectar: {e}"}}'

    if resp.status_code != 200:
        logger.error(f"distribuir_vendedora status {resp.status_code}: {resp.text[:300]}")
        return f'{{"success": false, "error": "HTTP {resp.status_code}: {resp.text[:200]}"}}'

    data = resp.json()
    seller_name = data.get("sellerName", "")
    if not seller_name:
        logger.error(f"distribuir_vendedora: sellerName vazio na resposta: {data}")
        return '{"success": false, "error": "sellerName vazio na resposta"}'

    run_context.session_state["assigned_seller_name"] = seller_name
    logger.info(f"distribuir_vendedora: lead={lead_id} atribuído a {seller_name}")
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

    # Trata "amanhã" e "hoje" diretamente
    if any(p in normalized_input for p in ('amanha', 'amanhã', 'tomorrow')):
        target = now + timedelta(days=1)
        date_with_year = f"{str(target.day).zfill(2)}/{str(target.month).zfill(2)}/{current_year}"
    elif 'hoje' in normalized_input or 'today' in normalized_input:
        date_with_year = f"{str(now.day).zfill(2)}/{str(now.month).zfill(2)}/{current_year}"

    # Tenta identificar dia da semana
    if not date_with_year:
        for name, wday in WEEKDAY_PT.items():
            if name in normalized_input:
                days_ahead = (wday - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
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
            f"{name_part}que bom te ajudar por aqui! "
            f"Vou te passar agora para a {seller_name}, que vai cuidar de tudo com voce "
            f"e fechar do jeitinho que voce quer. Ja ja ela fala com voce. Ate logo!"
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


@tool
async def enviar_foto_produto(run_context: RunContext, produto: str) -> str:
    """Envia a foto de um produto ao cliente e retorna a descrição para você falar sobre ele.

    Use quando o cliente demonstrar interesse em um tipo ou modelo de móvel que
    tenha foto disponível. Passe o nome do modelo ou a categoria
    (ex: "Poltrona Nuvem", "mesa de centro", "aparador").

    Se retornar encontrada=false, NÃO há foto desse produto — nesse caso siga
    normalmente com consultar_catalogo (lista com preços).

    Se retornar encontrada=true:
    - A foto já foi enviada ao cliente (no WhatsApp) OU virá no campo "foto_markdown".
    - Apresente o produto com base no campo "descricao", pergunte o que o cliente
      achou e diga que há mais modelos caso ele não goste.
    - Se vier "foto_markdown" preenchido, inclua-o EXATAMENTE na sua mensagem (é a imagem).
    - O preço desses produtos fica com a vendedora — não invente valor.
    """
    p = _achar_foto(produto)
    if not p:
        return '{"encontrada": false}'

    slug = p["slug"]
    if PUBLIC_BASE_URL:
        url = f"{PUBLIC_BASE_URL}/static/fotos/{slug}.jpg"
    else:
        url = f"/static/fotos/{slug}.jpg"

    conv = str(run_context.session_state.get("phone", ""))
    so_digitos = conv.replace("+", "")
    is_whatsapp = so_digitos.isdigit() and len(so_digitos) >= 10

    foto_enviada = False
    foto_markdown = ""
    if is_whatsapp and PUBLIC_BASE_URL:
        foto_enviada = await _send_media(conv, url)
    else:
        # Chat web (ou sem URL pública): devolve a imagem em markdown para renderizar
        foto_markdown = f"![{p['nome']}]({url})"

    out = {
        "encontrada": True,
        "nome": p["nome"],
        "descricao": p.get("descricao", ""),
        "foto_enviada": foto_enviada,
        "foto_markdown": foto_markdown,
    }
    return json.dumps(out, ensure_ascii=False)
