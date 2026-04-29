from fastapi import Depends

from src.backend.app.core.config import Settings, get_settings
from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.services import SyncOrchestrator
from src.backend.app.services.orchestrator import build_orchestrator


def get_saby_client(settings: Settings = Depends(get_settings)) -> SabyClient:
    return SabyClient(settings=settings)


def get_orchestrator(
    client: SabyClient = Depends(get_saby_client),
) -> SyncOrchestrator:
    return build_orchestrator(client)
