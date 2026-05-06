"""Route sub-package: AgentBench, auth, prompts, system e firebase."""

from app.routes.agentbench import agentbench_router
from app.routes.auth import auth_router
from app.routes.firebase_api import router as firebase_router
from app.routes.prompts import prompt_router
from app.routes.system import system_router

__all__ = [
    "agentbench_router",
    "auth_router",
    "prompt_router",
    "system_router",
    "firebase_router",
]
