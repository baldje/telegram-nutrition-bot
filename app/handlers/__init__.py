# app/handlers/__init__.py
from .start_handler import start_router
from .legal import router as legal_router
from .referral import router as referral_router
from .payments import router as payments_router
from .onboarding import onboarding_router
from .photo_handler import photo_router
from .main import main_router
__all__ = [
    'start_router',
    'legal_router',
    'referral_router',
    'payments_router',
    'onboarding_router',
    'photo_router',
    'main_router'
]