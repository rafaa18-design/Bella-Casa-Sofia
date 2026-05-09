"""Route sub-package: AgentBench, auth, prompts, system, firebase, reminders e webhook."""

from app.routes.agentbench import agentbench_router
from app.routes.auth import auth_router
from app.routes.firebase_api import router as firebase_router
from app.routes.prompts import prompt_router
from app.routes.reminders import router as reminders_router
from app.routes.system import system_router
from app.routes.webhook import router as webhook_router

__all__ = [
    "agentbench_router",
    "auth_router",
    "firebase_router",
    "prompt_router",
    "reminders_router",
    "system_router",
    "webhook_router",
]
