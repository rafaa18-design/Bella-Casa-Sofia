"""Agent module using Agno framework.

This module creates and configures the AI agent following AgentBench standard.
Integrates with Langfuse for observability and prompt management.
"""

import time

from agno.agent import Agent, RunOutput
from agno.models.anthropic import Claude
from agno.models.openai import OpenAIChat

from app.config import settings
from app.langfuse_client import create_trace, flush, get_prompt
from app.memory import memory
from app.models import (
    ActionTaken,
    DebugMetrics,
    FinalOutput,
    InputItem,
    LLMCall,
    Metrics,
    PromptDebug,
    RunDebugResponse,
    RunResponse,
    TrajectoryStage,
)
from app.tools import calculate, get_current_time


def get_model(model_id: str | None = None):
    """Get the appropriate model based on model_id."""
    model_id = model_id or settings.DEFAULT_MODEL

    if 'claude' in model_id.lower():
        return Claude(id=model_id)
    elif 'gpt' in model_id.lower() or 'o1' in model_id.lower():
        return OpenAIChat(id=model_id)
    else:
        # Default to Claude
        return Claude(id=settings.DEFAULT_MODEL)


def get_agent_instructions() -> str:
    """Get agent instructions from Langfuse or fallback to config."""
    return get_prompt(
        name=settings.AGENT_PROMPT_NAME,
        fallback=settings.AGENT_INSTRUCTIONS_FALLBACK,
    )


def create_agent(
    model_id: str | None = None,
    session_id: str | None = None,
    instructions: str | None = None,
) -> Agent:
    """Create an Agno agent with the specified configuration."""
    return Agent(
        model=get_model(model_id),
        tools=[get_current_time, calculate],
        instructions=instructions or get_agent_instructions(),
        add_history_to_context=True,
        session_id=session_id,
        markdown=True,
    )


def build_input_message(items: list[InputItem]) -> str:
    """Build the input message from multimodal items.

    For now, we only support text. Extend this to handle images, audio, etc.
    """
    text_parts = []
    for item in items:
        if item.type == 'text':
            text_parts.append(item.content)
        else:
            # TODO: Handle other types (image, audio, document, video)
            # For now, just note that we received them
            text_parts.append(f'[{item.type}: {item.filename or "unnamed"}]')
    return '\n'.join(text_parts)


def extract_actions_from_response(response: RunOutput) -> list[ActionTaken]:
    """Extract tool calls from the agent response."""
    actions = []
    if hasattr(response, 'tools') and response.tools:
        for tool_call in response.tools:
            actions.append(
                ActionTaken(
                    tool=tool_call.get('name', 'unknown'),
                    success=tool_call.get('success', True),
                    error=tool_call.get('error'),
                )
            )
    return actions


async def run_agent(
    conversation_id: str,
    items: list[InputItem],
    model: str | None = None,
) -> RunResponse:
    """Run the agent in production mode.

    Args:
        conversation_id: Unique conversation identifier
        items: List of input items (multimodal)
        model: Optional model override

    Returns:
        RunResponse with final output and metrics
    """
    start_time = time.perf_counter()

    # Get agent instructions from Langfuse
    instructions = get_agent_instructions()

    # Create Langfuse trace
    trace = create_trace(
        name='agent-run',
        session_id=conversation_id,
        metadata={
            'model': model or settings.DEFAULT_MODEL,
            'module_id': settings.MODULE_ID,
        },
        tags=['production', 'run'],
    )

    # Get or create conversation
    conv = memory.get_or_create(conversation_id)

    # Build input message
    user_message = build_input_message(items)

    # Create agent with session for conversation continuity
    agent = create_agent(
        model_id=model,
        session_id=conversation_id,
        instructions=instructions,
    )

    # Run the agent
    response: RunOutput = await agent.arun(user_message)

    # Store messages in memory
    memory.add_message(conversation_id, 'user', user_message)
    memory.add_message(conversation_id, 'assistant', response.content or '')

    # Calculate metrics
    latency_ms = (time.perf_counter() - start_time) * 1000
    tokens_used = None
    if hasattr(response, 'metrics') and response.metrics:
        tokens_used = getattr(response.metrics, 'total_tokens', None)

    # Update trace with output
    if trace:
        trace.update(
            input={'message': user_message},
            output={'response': response.content or ''},
            metadata={
                'latency_ms': latency_ms,
                'tokens_used': tokens_used,
            },
        )

    # Extract actions
    actions = extract_actions_from_response(response)

    # Flush Langfuse events
    flush()

    return RunResponse(
        conversation_id=conversation_id,
        final_output=FinalOutput(
            message=response.content or '',
            state=conv.state if conv.state else None,
            actions_taken=actions if actions else None,
        ),
        metrics=Metrics(
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            cost_estimate=None,
        ),
    )


async def run_agent_debug(
    conversation_id: str,
    items: list[InputItem],
    model: str | None = None,
) -> RunDebugResponse:
    """Run the agent in debug mode with full trajectory.

    Args:
        conversation_id: Unique conversation identifier
        items: List of input items (multimodal)
        model: Optional model override

    Returns:
        RunDebugResponse with trajectory and extended metrics
    """
    start_time = time.perf_counter()

    # Get agent instructions from Langfuse
    instructions = get_agent_instructions()

    # Create Langfuse trace
    trace = create_trace(
        name='agent-run-debug',
        session_id=conversation_id,
        metadata={
            'model': model or settings.DEFAULT_MODEL,
            'module_id': settings.MODULE_ID,
            'debug': True,
        },
        tags=['debug', 'run_debug'],
    )

    # Get or create conversation
    conv = memory.get_or_create(conversation_id)

    # Build input message
    user_message = build_input_message(items)

    # Create agent
    agent = create_agent(
        model_id=model,
        session_id=conversation_id,
        instructions=instructions,
    )

    # Run the agent
    response: RunOutput = await agent.arun(user_message)

    # Store messages in memory
    memory.add_message(conversation_id, 'user', user_message)
    memory.add_message(conversation_id, 'assistant', response.content or '')

    # Calculate metrics
    latency_ms = (time.perf_counter() - start_time) * 1000

    # Extract token info
    input_tokens = 0
    output_tokens = 0
    if hasattr(response, 'metrics') and response.metrics:
        input_tokens = getattr(response.metrics, 'input_tokens', 0) or 0
        output_tokens = getattr(response.metrics, 'output_tokens', 0) or 0

    # Update trace with output
    if trace:
        trace.update(
            input={'message': user_message},
            output={'response': response.content or ''},
            metadata={
                'latency_ms': latency_ms,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
            },
        )

    # Build trajectory (single stage for monolithic agent)
    trajectory = [
        TrajectoryStage(
            stage_id='main',
            type='agent',
            sequence=1,
            prompt_debug=PromptDebug(
                final_system_prompt_used=instructions,
            ),
            llm_calls=[
                LLMCall(
                    model=model or settings.DEFAULT_MODEL,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            ],
            latency_ms=latency_ms,
        )
    ]

    # Extract actions
    actions = extract_actions_from_response(response)

    # Flush Langfuse events
    flush()

    return RunDebugResponse(
        conversation_id=conversation_id,
        final_output=FinalOutput(
            message=response.content or '',
            state=conv.state if conv.state else None,
            actions_taken=actions if actions else None,
        ),
        trajectory=trajectory,
        metrics=DebugMetrics(
            total_latency_ms=latency_ms,
            total_tokens={'input': input_tokens, 'output': output_tokens},
            llm_calls=1,
        ),
    )
