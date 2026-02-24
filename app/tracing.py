"""OpenTelemetry tracing configuration.

Provides distributed tracing with OpenTelemetry, exporting traces to:
- Generic OTLP endpoint (e.g., Jaeger, Tempo) when OTEL_ENABLED=true
- Langfuse OTEL endpoint when LANGFUSE_ENABLED=true (for LLM cost/token tracking)

When Langfuse OTEL is enabled, Agno agent LLM calls are automatically
instrumented via OpenInference AgnoInstrumentor.
"""

import base64
import logging
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (BatchSpanProcessor,
                                            SimpleSpanProcessor)
from opentelemetry.trace import Span, Status, StatusCode

from app.config import settings

logger = logging.getLogger(__name__)

# Global tracer
_tracer: trace.Tracer | None = None


def setup_tracing(app=None):
    """Configure OpenTelemetry tracing.

    Sets up TracerProvider with exporters based on configuration:
    - OTEL_ENABLED: Adds gRPC OTLP exporter for generic tracing backends
    - LANGFUSE_ENABLED: Adds HTTP OTLP exporter for Langfuse + instruments Agno

    Args:
        app: Optional FastAPI app to instrument with OTEL.
    """
    global _tracer

    has_otel = settings.OTEL_ENABLED and settings.OTEL_EXPORTER_OTLP_ENDPOINT
    has_langfuse = (
        settings.LANGFUSE_ENABLED
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
    )

    if not has_otel and not has_langfuse:
        logger.info('OpenTelemetry tracing disabled (no exporters configured)')
        return

    try:
        # Create resource with service info
        resource = Resource.create(
            {
                'service.name': settings.MODULE_ID,
                'service.version': settings.MODULE_VERSION,
                'deployment.environment': settings.OTEL_ENVIRONMENT,
            }
        )

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Generic OTLP gRPC exporter (Jaeger, Tempo, etc.)
        if has_otel:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter as GrpcSpanExporter,
            )

            grpc_exporter = GrpcSpanExporter(
                endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
                insecure=settings.OTEL_EXPORTER_OTLP_INSECURE,
            )
            provider.add_span_processor(BatchSpanProcessor(grpc_exporter))
            logger.info(
                'OTEL gRPC exporter configured: %s',
                settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            )

        # Langfuse OTEL HTTP exporter + Agno instrumentation
        if has_langfuse:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter as HttpSpanExporter,
            )

            langfuse_auth = base64.b64encode(
                f'{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}'.encode()
            ).decode()

            langfuse_exporter = HttpSpanExporter(
                endpoint=f'{settings.LANGFUSE_BASE_URL}/api/public/otel/v1/traces',
                headers={'Authorization': f'Basic {langfuse_auth}'},
            )
            provider.add_span_processor(
                SimpleSpanProcessor(langfuse_exporter)
            )
            logger.info(
                'Langfuse OTEL exporter configured: %s',
                settings.LANGFUSE_BASE_URL,
            )

            # Instrument Agno with OpenInference
            from openinference.instrumentation.agno import AgnoInstrumentor

            AgnoInstrumentor().instrument(tracer_provider=provider)
            logger.info('Agno instrumented with OpenInference → Langfuse')

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Get tracer
        _tracer = trace.get_tracer(
            settings.MODULE_ID,
            settings.MODULE_VERSION,
        )

        # Instrument FastAPI if app provided and generic OTEL enabled
        if app is not None and has_otel:
            from opentelemetry.instrumentation.fastapi import \
                FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls='/health,/metrics',
            )
            logger.info('FastAPI instrumented with OpenTelemetry')

    except Exception as e:
        logger.error('Failed to configure OpenTelemetry: %s', e)


def get_tracer() -> trace.Tracer:
    """Get the configured tracer.

    Returns a no-op tracer if tracing is not configured.
    """
    global _tracer
    if _tracer is None:
        return trace.get_tracer(settings.MODULE_ID)
    return _tracer


@contextmanager
def create_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
):
    """Create a new span as a context manager.

    Args:
        name: Span name.
        attributes: Optional span attributes.
        kind: Span kind (internal, server, client, etc.).

    Yields:
        The created span.

    Example:
        with create_span('process_request', {'user_id': user_id}) as span:
            result = process(request)
            span.set_attribute('result_size', len(result))
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name, kind=kind) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def add_span_attributes(attributes: dict[str, Any]):
    """Add attributes to the current span.

    Args:
        attributes: Dictionary of attributes to add.
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def record_exception(
    exception: Exception, attributes: dict[str, Any] | None = None
):
    """Record an exception in the current span.

    Args:
        exception: The exception to record.
        attributes: Optional additional attributes.
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        span.record_exception(exception, attributes=attributes)
        span.set_status(Status(StatusCode.ERROR, str(exception)))


def get_current_trace_id() -> str | None:
    """Get the current trace ID as a hex string.

    Returns:
        Trace ID or None if no active span.
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, '032x')
    return None


def get_current_span_id() -> str | None:
    """Get the current span ID as a hex string.

    Returns:
        Span ID or None if no active span.
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().span_id, '016x')
    return None


def shutdown_tracing():
    """Shutdown tracing and flush pending spans."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, 'shutdown'):
        provider.shutdown()
        logger.info('OpenTelemetry tracing shut down')
