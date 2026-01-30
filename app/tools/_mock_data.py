"""Dados mockados para desenvolvimento e testes.

⚠️  IMPORTANTE: Estes dados são APENAS para desenvolvimento e testes.
Em produção, as tools devem consultar APIs reais, bancos de dados
ou serviços externos. O mock existe para permitir validar o pipeline
completo (auth, metrics, tracing, state, etc.) sem dependências externas.

Para substituir por dados reais:
1. Remova este arquivo
2. Atualize cada tool para consultar a fonte de dados real
3. Mantenha a mesma interface (assinatura e retorno) das tools
"""

DENTISTAS = {
    "DRA001": {
        "nome": "Dra. Maria Silva",
        "especialidade": "Clínica Geral e Estética",
        "crm": "CRO-SP 12345",
    },
    "DR002": {
        "nome": "Dr. Carlos Mendes",
        "especialidade": "Ortodontia e Implantodontia",
        "crm": "CRO-SP 23456",
    },
    "DRA003": {
        "nome": "Dra. Juliana Costa",
        "especialidade": "Endodontia e Periodontia",
        "crm": "CRO-SP 34567",
    },
}

SERVICOS = {
    "limpeza": {
        "nome": "Limpeza e Profilaxia",
        "preco": 150.00,
        "duracao_min": 30,
        "descricao": "Remoção de tártaro, placa bacteriana e polimento dental.",
    },
    "clareamento": {
        "nome": "Clareamento Dental",
        "preco": 800.00,
        "duracao_min": 60,
        "descricao": "Clareamento a laser em consultório com gel de peróxido de hidrogênio.",
    },
    "restauracao": {
        "nome": "Restauração em Resina",
        "preco": 250.00,
        "duracao_min": 45,
        "descricao": "Restauração estética com resina composta fotopolimerizável.",
    },
    "canal": {
        "nome": "Tratamento de Canal",
        "preco": 900.00,
        "duracao_min": 90,
        "descricao": "Endodontia completa com obturação e raio-X de controle.",
    },
    "extracao": {
        "nome": "Extração Simples",
        "preco": 200.00,
        "duracao_min": 30,
        "descricao": "Extração de dente com anestesia local e orientações pós-operatórias.",
    },
    "implante": {
        "nome": "Implante Dentário",
        "preco": 3500.00,
        "duracao_min": 120,
        "descricao": "Implante de titânio com coroa de porcelana. Inclui planejamento com tomografia.",
    },
    "ortodontia": {
        "nome": "Ortodontia (mensalidade)",
        "preco": 350.00,
        "duracao_min": 30,
        "descricao": "Manutenção mensal do aparelho ortodôntico fixo ou alinhadores.",
    },
    "avaliacao": {
        "nome": "Avaliação e Diagnóstico",
        "preco": 0.00,
        "duracao_min": 30,
        "descricao": "Consulta inicial gratuita com avaliação clínica e radiográfica.",
    },
    "protese": {
        "nome": "Prótese Fixa (coroa)",
        "preco": 1200.00,
        "duracao_min": 60,
        "descricao": "Coroa em porcelana sobre dente preparado. Inclui moldagem e provisório.",
    },
    "faceta": {
        "nome": "Faceta de Porcelana",
        "preco": 1500.00,
        "duracao_min": 60,
        "descricao": "Laminado cerâmico ultrafino para harmonização do sorriso.",
    },
}

PACIENTES = {
    "PAC001": {
        "nome": "João Pereira",
        "cpf": "123.456.789-00",
        "telefone": "(11) 98765-4321",
        "email": "joao.pereira@email.com",
        "data_nascimento": "1985-03-15",
        "convenio": "OdontoPrev",
        "historico": [
            {"data": "2024-06-10", "servico": "limpeza", "dentista": "DRA001", "obs": "Tártaro moderado removido"},
            {"data": "2024-09-20", "servico": "restauracao", "dentista": "DRA001", "obs": "Restauração dente 36"},
            {"data": "2025-01-15", "servico": "limpeza", "dentista": "DRA001", "obs": "Manutenção semestral"},
        ],
    },
    "PAC002": {
        "nome": "Ana Santos",
        "cpf": "987.654.321-00",
        "telefone": "(11) 91234-5678",
        "email": "ana.santos@email.com",
        "data_nascimento": "1992-07-22",
        "convenio": None,
        "historico": [
            {"data": "2024-11-05", "servico": "avaliacao", "dentista": "DR002", "obs": "Indicado aparelho ortodôntico"},
            {"data": "2024-12-01", "servico": "ortodontia", "dentista": "DR002", "obs": "Instalação aparelho fixo"},
        ],
    },
    "PAC003": {
        "nome": "Carlos Oliveira",
        "cpf": "456.789.123-00",
        "telefone": "(11) 99876-5432",
        "email": "carlos.oliveira@email.com",
        "data_nascimento": "1978-11-30",
        "convenio": "Amil Dental",
        "historico": [
            {"data": "2024-08-14", "servico": "canal", "dentista": "DRA003", "obs": "Canal dente 46 - 3 sessões"},
            {"data": "2024-10-02", "servico": "protese", "dentista": "DRA003", "obs": "Coroa de porcelana dente 46"},
        ],
    },
    "PAC004": {
        "nome": "Mariana Lima",
        "cpf": "321.654.987-00",
        "telefone": "(11) 97654-3210",
        "email": "mariana.lima@email.com",
        "data_nascimento": "2000-01-08",
        "convenio": "SulAmérica Odonto",
        "historico": [
            {"data": "2025-01-10", "servico": "clareamento", "dentista": "DRA001", "obs": "Clareamento a laser - 3 tons"},
        ],
    },
    "PAC005": {
        "nome": "Roberto Souza",
        "cpf": "654.321.987-00",
        "telefone": "(11) 96543-2109",
        "email": "roberto.souza@email.com",
        "data_nascimento": "1965-05-18",
        "convenio": "OdontoPrev",
        "historico": [
            {"data": "2024-07-20", "servico": "implante", "dentista": "DR002", "obs": "Implante dente 14 - fase 1"},
            {"data": "2024-10-20", "servico": "implante", "dentista": "DR002", "obs": "Implante dente 14 - coroa"},
            {"data": "2025-01-20", "servico": "limpeza", "dentista": "DRA001", "obs": "Controle pós-implante"},
        ],
    },
}

# Mapeamento de canal (conversation_id) → paciente.
# Em produção, o conversation_id é o identificador único do canal (ex: número
# de telefone no WhatsApp, ID da conta, etc). Aqui usamos telefones como chave para simular isso.
# IDs não mapeados são tratados como pacientes novos.
CLIENTES_POR_CANAL: dict[str, str] = {
    pac["telefone"]: pid
    for pid, pac in PACIENTES.items()
}

CONVENIOS = {
    "OdontoPrev": {
        "nome": "OdontoPrev",
        "cobertura": {
            "limpeza": 1.0,
            "restauracao": 0.8,
            "canal": 0.7,
            "extracao": 1.0,
            "avaliacao": 1.0,
            "ortodontia": 0.5,
        },
        "carencia_dias": 30,
        "observacao": "Sem cobertura para implante, clareamento, prótese e faceta.",
    },
    "Amil Dental": {
        "nome": "Amil Dental",
        "cobertura": {
            "limpeza": 1.0,
            "restauracao": 1.0,
            "canal": 0.8,
            "extracao": 1.0,
            "avaliacao": 1.0,
            "protese": 0.5,
        },
        "carencia_dias": 60,
        "observacao": "Sem cobertura para implante, clareamento, ortodontia e faceta.",
    },
    "SulAmérica Odonto": {
        "nome": "SulAmérica Odonto",
        "cobertura": {
            "limpeza": 1.0,
            "restauracao": 0.9,
            "canal": 0.9,
            "extracao": 1.0,
            "avaliacao": 1.0,
            "ortodontia": 0.6,
            "protese": 0.4,
        },
        "carencia_dias": 45,
        "observacao": "Sem cobertura para implante, clareamento e faceta.",
    },
    "Bradesco Dental": {
        "nome": "Bradesco Dental",
        "cobertura": {
            "limpeza": 1.0,
            "restauracao": 1.0,
            "canal": 1.0,
            "extracao": 1.0,
            "avaliacao": 1.0,
            "ortodontia": 0.7,
            "implante": 0.3,
            "protese": 0.6,
        },
        "carencia_dias": 90,
        "observacao": "Plano premium. Sem cobertura para clareamento e faceta.",
    },
}

# Slots de horário disponíveis (8h-18h, intervalos de 30min)
HORARIOS_BASE = [
    f"{h:02d}:{m:02d}"
    for h in range(8, 18)
    for m in (0, 30)
]
