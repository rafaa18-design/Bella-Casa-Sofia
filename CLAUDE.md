# Asani AI Agent Template

## Overview

This is an **AI Agent Module Template** that follows the **AgentBench Standard**. It uses the **Agno** framework for agent implementation, **FastAPI** for the API layer, and **Langfuse** for observability and prompt management.

## Project Structure

```
asani-ai-agent-template/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app with AgentBench endpoints
│   ├── agent.py             # Agno agent configuration
│   ├── models.py            # Pydantic models (AgentBench standard)
│   ├── memory.py            # Conversation memory management
│   ├── config.py            # Application settings
│   ├── langfuse_client.py   # Langfuse integration
│   └── tools/               # Custom tools
│       └── __init__.py
├── tests/                   # Test files
├── pyproject.toml           # uv project configuration
├── .env.example             # Environment variables template
└── CLAUDE.md                # This file
```

## Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn app.main:app --reload

# Run with Python directly
uv run python -m app.main

# Run tests
uv run pytest

# Linting and formatting
uv run ruff check app/
uv run isort app/
uv run blue app/
```

## AgentBench Standard

This template implements the three required endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metadata` | GET | Module capabilities and configuration |
| `/run` | POST | Production execution |
| `/run_debug` | POST | Debug execution with full trajectory |

### Request Format

```json
{
  "input": [
    { "type": "text", "content": "Hello!" }
  ],
  "conversation_id": "conv_123",
  "model": "claude-sonnet-4-20250514"
}
```

### Response Format (/run)

```json
{
  "conversation_id": "conv_123",
  "final_output": {
    "message": "Hello! How can I help you?",
    "state": {},
    "actions_taken": []
  },
  "metrics": {
    "latency_ms": 320,
    "tokens_used": 57
  }
}
```

## Langfuse Integration

The template integrates with [Langfuse](https://langfuse.com) for:

### Observability (Tracing)

Every `/run` and `/run_debug` call creates a trace in Langfuse with:
- Session ID (conversation_id)
- Input/output messages
- Latency and token metrics
- Tags for filtering (production/debug)

### Prompt Management

Instead of hardcoding prompts, manage them in Langfuse:

1. **Create a prompt in Langfuse UI** named `agent-instructions`
2. **Add the `production` label** to the version you want to use
3. The agent automatically fetches the latest production prompt

Variables are supported using `{{variableName}}` syntax.

### Configuration

```bash
# .env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_ENABLED=true

# Prompt configuration
AGENT_PROMPT_NAME=agent-instructions
AGENT_INSTRUCTIONS_FALLBACK=You are a helpful AI assistant.
```

If Langfuse is not configured or unavailable, the fallback prompt is used.

## Customization

### Adding Tools

Edit `app/tools/__init__.py`:

```python
from agno.tools import tool

@tool
def my_custom_tool(param: str) -> str:
    """Tool description for the model."""
    return f"Result: {param}"
```

Then add to the agent in `app/agent.py`:

```python
from app.tools import my_custom_tool

def create_agent(...):
    return Agent(
        ...
        tools=[get_current_time, calculate, my_custom_tool],
    )
```

### Changing the Model

Set the `DEFAULT_MODEL` environment variable or pass `model` in the request.

Supported models:
- Claude: `claude-sonnet-4-20250514`, `claude-3-5-sonnet-20241022`
- OpenAI: `gpt-4o`, `gpt-4-turbo`

### Persistent Memory

For production, replace the in-memory storage in `app/memory.py` with:
- Redis for distributed cache
- PostgreSQL with Agno's `PostgresDb`
- Any other database backend

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MODULE_ID` | Unique module identifier | `asani-agent-template` |
| `MODULE_VERSION` | Semantic version | `1.0.0` |
| `DEFAULT_MODEL` | Default LLM model | `claude-sonnet-4-20250514` |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `AGENT_PROMPT_NAME` | Langfuse prompt name | `agent-instructions` |
| `AGENT_INSTRUCTIONS_FALLBACK` | Fallback prompt | `You are a helpful AI assistant.` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | - |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | - |
| `LANGFUSE_BASE_URL` | Langfuse API URL | `https://cloud.langfuse.com` |
| `LANGFUSE_ENABLED` | Enable Langfuse | `true` |
| `HOST` | Server host | `0.0.0.0` |
| `PORT` | Server port | `8000` |
