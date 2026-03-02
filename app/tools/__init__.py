"""Ferramentas do agente de atendimento.

Tools agrupadas por domínio:
- consultas: agendar, cancelar, verificar disponibilidade
- pacientes: buscar, histórico, verificar cliente, convênios
- catalogo: listar serviços, calcular orçamento, obter data/hora
- sessao: salvar dados cliente, salvar preferências, ver contexto

⚠️  IMPORTANTE: As tools deste template usam dados mockados (_mock_data.py)
para desenvolvimento e testes. Em produção, substitua por integrações reais
(APIs, bancos de dados, serviços externos).
"""

from app.tools.catalogo import calcular_orcamento, listar_servicos, obter_data_hora
from app.tools.consultas import agendar_consulta, cancelar_consulta, verificar_disponibilidade
from app.tools.formatar_contexto import formatar_contexto_completo, formatar_contexto_state
from app.tools.pacientes import (
    buscar_paciente,
    consultar_convenios,
    consultar_historico_paciente,
    verificar_cliente,
)
from app.tools.sessao import salvar_dados_cliente, salvar_preferencias, ver_contexto_sessao

__all__ = [
    "listar_servicos",
    "verificar_disponibilidade",
    "agendar_consulta",
    "cancelar_consulta",
    "buscar_paciente",
    "consultar_historico_paciente",
    "consultar_convenios",
    "calcular_orcamento",
    "salvar_dados_cliente",
    "salvar_preferencias",
    "ver_contexto_sessao",
    "verificar_cliente",
    "formatar_contexto_state",
    "formatar_contexto_completo",
    "obter_data_hora",
]
