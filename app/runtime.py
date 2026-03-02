"""Custom runtime replacing agno.tools, agno.run, agno.exceptions.

Provides:
- RunContext dataclass (replaces agno.run.RunContext)
- RetryAgentRun / StopAgentRun exceptions (replaces agno.exceptions)
- @tool decorator (replaces agno.tools.tool)
- ToolRegistry (registers and executes tools)
"""

import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# RunContext (replaces agno.run.RunContext)
# =============================================================================


@dataclass
class RunContext:
    """Context passed to tool functions during agent execution."""

    session_state: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    user_id: str | None = None


# =============================================================================
# Exceptions (replaces agno.exceptions)
# =============================================================================


class RetryAgentRun(Exception):
    """Raised by a tool to send feedback to the LLM and retry."""

    def __init__(self, message: str = ''):
        self.message = message
        super().__init__(message)


class StopAgentRun(Exception):
    """Raised by a tool to stop the agent loop immediately."""

    def __init__(self, message: str = ''):
        self.message = message
        super().__init__(message)


# =============================================================================
# Tool Definition
# =============================================================================


@dataclass
class ToolDefinition:
    """A registered tool with its metadata and callable."""

    name: str
    description: str
    parameters: dict[str, Any]  # OpenAI JSON Schema format
    func: Callable


# =============================================================================
# @tool Decorator (replaces agno.tools.tool)
# =============================================================================

# Python type → JSON Schema type mapping
_TYPE_MAP: dict[type, str] = {
    str: 'string',
    int: 'integer',
    float: 'number',
    bool: 'boolean',
    list: 'array',
    dict: 'object',
}


def _python_type_to_json_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to JSON Schema."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {'type': 'string'}

    # Handle Optional / Union types
    origin = getattr(annotation, '__origin__', None)
    if origin is not None:
        args = getattr(annotation, '__args__', ())
        # list[X] → {"type": "array", "items": ...}
        if origin is list:
            items = _python_type_to_json_schema(args[0]) if args else {'type': 'string'}
            return {'type': 'array', 'items': items}
        # dict[K, V] → {"type": "object"}
        if origin is dict:
            return {'type': 'object'}

    return {'type': _TYPE_MAP.get(annotation, 'string')}


def tool(func: Callable) -> ToolDefinition:
    """Decorator that converts a function into a ToolDefinition.

    Extracts the function signature and docstring to build an
    OpenAI-compatible JSON Schema for tool calling.

    The `run_context` parameter (if present) is filtered out from
    the schema — it will be injected by the ToolRegistry at execution time.
    """
    sig = inspect.signature(func)
    doc = (func.__doc__ or '').strip()
    # Use first line of docstring as description
    description = doc.split('\n')[0] if doc else func.__name__

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # Skip run_context — injected at execution time
        if param_name == 'run_context':
            continue

        schema = _python_type_to_json_schema(param.annotation)

        # Add description from docstring Args section if available
        properties[param_name] = schema

        # Parameters without defaults are required
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        else:
            # Include default in schema for documentation
            if param.default is not None and param.default != '':
                properties[param_name]['default'] = param.default

    parameters_schema: dict[str, Any] = {
        'type': 'object',
        'properties': properties,
    }
    if required:
        parameters_schema['required'] = required

    return ToolDefinition(
        name=func.__name__,
        description=description,
        parameters=parameters_schema,
        func=func,
    )


# =============================================================================
# ToolRegistry
# =============================================================================


class ToolRegistry:
    """Registry for managing and executing tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool_def: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool_def.name] = tool_def

    def get_definitions(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool definitions for litellm."""
        definitions = []
        for td in self._tools.values():
            definitions.append({
                'type': 'function',
                'function': {
                    'name': td.name,
                    'description': td.description,
                    'parameters': td.parameters,
                },
            })
        return definitions

    async def execute(
        self,
        name: str,
        args: dict[str, Any],
        run_context: RunContext,
    ) -> str:
        """Execute a tool by name, injecting RunContext if needed.

        Args:
            name: The tool name to execute.
            args: The arguments parsed from the LLM tool call.
            run_context: The current RunContext to inject.

        Returns:
            The tool result as a string.

        Raises:
            RetryAgentRun: If the tool wants the LLM to retry.
            StopAgentRun: If the tool wants to stop the agent loop.
        """
        tool_def = self._tools.get(name)
        if tool_def is None:
            return f'Error: unknown tool "{name}"'

        # Check if function expects run_context
        sig = inspect.signature(tool_def.func)
        if 'run_context' in sig.parameters:
            args = {**args, 'run_context': run_context}

        try:
            # Support both sync and async functions
            result = tool_def.func(**args)
            if inspect.isawaitable(result):
                result = await result
            return str(result) if result is not None else ''
        except RetryAgentRun:
            raise
        except StopAgentRun:
            raise
        except Exception as e:
            logger.error(f'Tool "{name}" execution error: {e}')
            return f'Error executing tool "{name}": {e}'
