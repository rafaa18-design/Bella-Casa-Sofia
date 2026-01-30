"""Testes para as ferramentas de atendimento da clínica odontológica."""

import pytest
from agno.exceptions import RetryAgentRun, StopAgentRun
from agno.run import RunContext

from app.tools import (
    agendar_consulta,
    buscar_paciente,
    calcular_orcamento,
    cancelar_consulta,
    consultar_convenios,
    consultar_historico_paciente,
    listar_servicos,
    verificar_disponibilidade,
)


# Helper to get the actual callable function from Agno Function wrapper
def call_tool(tool_func, *args, **kwargs):
    """Call a tool function, handling Agno Function wrapper."""
    if hasattr(tool_func, 'func'):
        return tool_func.func(*args, **kwargs)
    elif hasattr(tool_func, 'entrypoint'):
        return tool_func.entrypoint(*args, **kwargs)
    else:
        return tool_func(*args, **kwargs)


def create_run_context(session_state: dict | None = None) -> RunContext:
    """Create a RunContext for testing tools."""
    return RunContext(
        run_id='test-run-id',
        session_id='test-session-id',
        session_state=session_state,
    )


# =============================================================================
# Listar Serviços
# =============================================================================


class TestListarServicos:
    """Testes para listar_servicos."""

    def test_lista_todos_servicos(self):
        result = call_tool(listar_servicos)
        assert 'Clínica Sorriso' in result
        assert 'Limpeza e Profilaxia' in result
        assert 'Clareamento Dental' in result
        assert 'Tratamento de Canal' in result
        assert 'Implante Dentário' in result
        assert 'Avaliação e Diagnóstico' in result

    def test_mostra_precos(self):
        result = call_tool(listar_servicos)
        assert 'R$ 150.00' in result  # limpeza
        assert 'Gratuito' in result  # avaliação

    def test_mostra_duracao(self):
        result = call_tool(listar_servicos)
        assert '30 min' in result
        assert '90 min' in result  # canal


# =============================================================================
# Verificar Disponibilidade
# =============================================================================


class TestVerificarDisponibilidade:
    """Testes para verificar_disponibilidade."""

    def test_data_invalida_raises_retry(self):
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(verificar_disponibilidade, '15/02/2025')
        assert 'formato inválido' in str(exc.value)

    def test_data_passada_raises_retry(self):
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(verificar_disponibilidade, '2020-01-01')
        assert 'datas passadas' in str(exc.value)

    def test_domingo_raises_retry(self):
        # Encontrar um domingo futuro
        from datetime import datetime, timedelta
        hoje = datetime.now()
        dias_ate_domingo = (6 - hoje.weekday()) % 7
        if dias_ate_domingo == 0:
            dias_ate_domingo = 7
        domingo = (hoje + timedelta(days=dias_ate_domingo)).strftime('%Y-%m-%d')

        with pytest.raises(RetryAgentRun) as exc:
            call_tool(verificar_disponibilidade, domingo)
        assert 'domingos' in str(exc.value)

    def test_dentista_inexistente_raises_retry(self):
        from datetime import datetime, timedelta
        data_futura = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        # Pular se for domingo
        d = datetime.strptime(data_futura, '%Y-%m-%d')
        if d.weekday() == 6:
            data_futura = (d + timedelta(days=1)).strftime('%Y-%m-%d')

        with pytest.raises(RetryAgentRun) as exc:
            call_tool(verificar_disponibilidade, data_futura, 'Dr. Inexistente')
        assert 'não encontrado' in str(exc.value)

    def test_retorna_horarios_validos(self):
        from datetime import datetime, timedelta
        # Encontrar um dia útil futuro (segunda a sexta)
        hoje = datetime.now()
        for i in range(1, 8):
            data = hoje + timedelta(days=i)
            if data.weekday() < 5:  # seg-sex
                data_str = data.strftime('%Y-%m-%d')
                break

        result = call_tool(verificar_disponibilidade, data_str, 'Maria')
        assert 'Dra. Maria Silva' in result
        assert ':' in result  # Contém horários no formato HH:MM

    def test_mostra_todos_dentistas_sem_filtro(self):
        from datetime import datetime, timedelta
        hoje = datetime.now()
        for i in range(1, 8):
            data = hoje + timedelta(days=i)
            if data.weekday() < 5:
                data_str = data.strftime('%Y-%m-%d')
                break

        result = call_tool(verificar_disponibilidade, data_str)
        assert 'Dra. Maria Silva' in result
        assert 'Dr. Carlos Mendes' in result
        assert 'Dra. Juliana Costa' in result


# =============================================================================
# Agendar Consulta
# =============================================================================


class TestAgendarConsulta:
    """Testes para agendar_consulta."""

    def test_servico_invalido_raises_retry(self):
        ctx = create_run_context({})
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(agendar_consulta, ctx, 'João', '2025-06-10', '09:00', 'raio_x', 'DRA001')
        assert 'não encontrado' in str(exc.value)

    def test_dentista_invalido_raises_retry(self):
        ctx = create_run_context({})
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(agendar_consulta, ctx, 'João', '2025-06-10', '09:00', 'limpeza', 'DR999')
        assert 'não encontrado' in str(exc.value)

    def test_data_invalida_raises_retry(self):
        ctx = create_run_context({})
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(agendar_consulta, ctx, 'João', 'invalido', '09:00', 'limpeza', 'DRA001')
        assert 'formato inválido' in str(exc.value)

    def test_horario_invalido_raises_retry(self):
        ctx = create_run_context({})
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(agendar_consulta, ctx, 'João', '2025-06-10', '09:15', 'limpeza', 'DRA001')
        assert 'inválido' in str(exc.value)

    def test_agendamento_salva_no_session_state(self):
        ctx = create_run_context({})
        # Encontrar um horário disponível
        from app.tools._helpers import gerar_agenda_mock as _gerar_agenda_mock
        data = '2025-06-10'
        disponiveis = _gerar_agenda_mock(data, 'DRA001')
        horario = disponiveis[0]

        result = call_tool(agendar_consulta, ctx, 'João Silva', data, horario, 'limpeza', 'DRA001')
        assert 'agendada com sucesso' in result
        assert 'João Silva' in result
        assert 'Limpeza e Profilaxia' in result
        assert 'Dra. Maria Silva' in result

        # Verifica session state
        assert 'agendamentos' in ctx.session_state
        assert len(ctx.session_state['agendamentos']) == 1
        assert ctx.session_state['agendamentos'][0]['status'] == 'confirmado'
        assert ctx.session_state['ultimo_agendamento'] is not None


# =============================================================================
# Cancelar Consulta
# =============================================================================


class TestCancelarConsulta:
    """Testes para cancelar_consulta."""

    def test_sem_agendamentos_raises_retry(self):
        ctx = create_run_context({})
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(cancelar_consulta, ctx, 'CON-ABC123')
        assert 'Nenhuma consulta' in str(exc.value)

    def test_consulta_inexistente_raises_retry(self):
        ctx = create_run_context({
            'agendamentos': [
                {'id': 'CON-AAA111', 'status': 'confirmado', 'paciente': 'João',
                 'data': '2025-06-10', 'horario': '09:00', 'servico_nome': 'Limpeza'},
            ]
        })
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(cancelar_consulta, ctx, 'CON-ZZZ999')
        assert 'não encontrada' in str(exc.value)

    def test_cancelamento_com_sucesso(self):
        ctx = create_run_context({
            'agendamentos': [
                {'id': 'CON-AAA111', 'status': 'confirmado', 'paciente': 'João',
                 'data': '2025-06-10', 'horario': '09:00', 'servico_nome': 'Limpeza'},
            ]
        })
        result = call_tool(cancelar_consulta, ctx, 'CON-AAA111')
        assert 'cancelada com sucesso' in result
        assert ctx.session_state['agendamentos'][0]['status'] == 'cancelado'

    def test_cancelar_ja_cancelada_raises_retry(self):
        ctx = create_run_context({
            'agendamentos': [
                {'id': 'CON-AAA111', 'status': 'cancelado', 'paciente': 'João',
                 'data': '2025-06-10', 'horario': '09:00', 'servico_nome': 'Limpeza'},
            ]
        })
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(cancelar_consulta, ctx, 'CON-AAA111')
        assert 'já foi cancelada' in str(exc.value)


# =============================================================================
# Buscar Paciente
# =============================================================================


class TestBuscarPaciente:
    """Testes para buscar_paciente."""

    def test_busca_por_nome_completo(self):
        result = call_tool(buscar_paciente, 'João Pereira')
        assert 'João Pereira' in result
        assert 'PAC001' in result

    def test_busca_por_nome_parcial(self):
        result = call_tool(buscar_paciente, 'Ana')
        assert 'Ana Santos' in result
        assert 'PAC002' in result

    def test_busca_case_insensitive(self):
        result = call_tool(buscar_paciente, 'carlos')
        assert 'Carlos Oliveira' in result

    def test_paciente_nao_encontrado_raises_retry(self):
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(buscar_paciente, 'Paciente Inexistente')
        assert 'Nenhum paciente' in str(exc.value)

    def test_mostra_convenio(self):
        result = call_tool(buscar_paciente, 'João')
        assert 'OdontoPrev' in result

    def test_mostra_particular_sem_convenio(self):
        result = call_tool(buscar_paciente, 'Ana Santos')
        assert 'Particular' in result


# =============================================================================
# Consultar Histórico
# =============================================================================


class TestConsultarHistorico:
    """Testes para consultar_historico_paciente."""

    def test_historico_existente(self):
        result = call_tool(consultar_historico_paciente, 'PAC001')
        assert 'João Pereira' in result
        assert 'Limpeza e Profilaxia' in result
        assert 'Restauração em Resina' in result
        assert 'Dra. Maria Silva' in result

    def test_paciente_inexistente_raises_retry(self):
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(consultar_historico_paciente, 'PAC999')
        assert 'não encontrado' in str(exc.value)

    def test_mostra_proxima_revisao(self):
        result = call_tool(consultar_historico_paciente, 'PAC001')
        assert 'Próxima revisão' in result


# =============================================================================
# Consultar Convênios
# =============================================================================


class TestConsultarConvenios:
    """Testes para consultar_convenios."""

    def test_lista_todos_convenios(self):
        result = call_tool(consultar_convenios)
        assert 'OdontoPrev' in result
        assert 'Amil Dental' in result
        assert 'SulAmérica Odonto' in result
        assert 'Bradesco Dental' in result

    def test_mostra_cobertura(self):
        result = call_tool(consultar_convenios)
        assert '100%' in result  # limpeza é sempre 100%
        assert 'Carência' in result

    def test_mostra_desconto_particular(self):
        result = call_tool(consultar_convenios)
        assert '10% de desconto' in result


# =============================================================================
# Calcular Orçamento
# =============================================================================


class TestCalcularOrcamento:
    """Testes para calcular_orcamento."""

    def test_servico_unico_particular(self):
        result = call_tool(calcular_orcamento, 'limpeza')
        assert 'R$ 150.00' in result
        assert 'Particular' in result

    def test_multiplos_servicos(self):
        result = call_tool(calcular_orcamento, 'limpeza,restauracao')
        assert 'Limpeza e Profilaxia' in result
        assert 'Restauração em Resina' in result
        assert 'R$ 400.00' in result  # 150 + 250

    def test_com_convenio(self):
        result = call_tool(calcular_orcamento, 'limpeza,restauracao', 'OdontoPrev')
        assert 'OdontoPrev' in result
        assert '100%' in result  # limpeza
        assert '80%' in result  # restauracao

    def test_servico_invalido_raises_retry(self):
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(calcular_orcamento, 'servico_falso')
        assert 'não encontrados' in str(exc.value)

    def test_convenio_invalido_raises_retry(self):
        with pytest.raises(RetryAgentRun) as exc:
            call_tool(calcular_orcamento, 'limpeza', 'ConvenioFalso')
        assert 'não encontrado' in str(exc.value)

    def test_mostra_parcelamento_particular(self):
        result = call_tool(calcular_orcamento, 'canal')
        assert 'Parcelado 3x' in result
        assert 'vista' in result

    def test_mostra_tempo_estimado(self):
        result = call_tool(calcular_orcamento, 'limpeza,canal')
        assert 'Tempo total estimado' in result
        assert '120 minutos' in result  # 30 + 90

    def test_servico_gratuito(self):
        result = call_tool(calcular_orcamento, 'avaliacao')
        assert 'Gratuito' in result


# =============================================================================
# Integration Tests
# =============================================================================


class TestFluxoCompleto:
    """Testes de integração para fluxos completos de atendimento."""

    def test_fluxo_buscar_e_consultar_historico(self):
        """Buscar paciente e consultar histórico."""
        result_busca = call_tool(buscar_paciente, 'Roberto')
        assert 'PAC005' in result_busca

        result_hist = call_tool(consultar_historico_paciente, 'PAC005')
        assert 'Implante Dentário' in result_hist
        assert 'Dr. Carlos Mendes' in result_hist

    def test_fluxo_agendar_e_cancelar(self):
        """Agendar e depois cancelar uma consulta."""
        ctx = create_run_context({})

        from app.tools._helpers import gerar_agenda_mock as _gerar_agenda_mock
        data = '2025-06-10'
        disponiveis = _gerar_agenda_mock(data, 'DRA001')
        horario = disponiveis[0]

        # Agendar
        result = call_tool(agendar_consulta, ctx, 'Maria Teste', data, horario, 'limpeza', 'DRA001')
        assert 'agendada com sucesso' in result

        # Pegar ID da consulta
        consulta_id = ctx.session_state['agendamentos'][0]['id']

        # Cancelar
        result = call_tool(cancelar_consulta, ctx, consulta_id)
        assert 'cancelada com sucesso' in result
        assert ctx.session_state['agendamentos'][0]['status'] == 'cancelado'

    def test_fluxo_orcamento_com_convenio(self):
        """Calcular orçamento usando convênio do paciente."""
        result_busca = call_tool(buscar_paciente, 'João')
        assert 'OdontoPrev' in result_busca

        result_orc = call_tool(calcular_orcamento, 'limpeza,restauracao', 'OdontoPrev')
        assert 'OdontoPrev' in result_orc
        assert 'Cobertura do convênio' in result_orc
