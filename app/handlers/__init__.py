# app/handlers/__init__.py
from .start_handler import start_router
from .onboarding import onboarding_router
from .photo_handler import photo_router
from .payments import router as payments_router  # ✅ ИМПОРТИРУЕМ ПЛАТЕЖИ
from .main import main_router
from .legal import router as legal_router      # НОВЫЙ
from .referral import router as referral_router # НОВЫЙ

__all__ = [
    'start_router',
    'onboarding_router',
    'photo_router',
    'payments_router',  # ✅ ДОБАВЛЯЕМ В __all__
    'main_router',
    'legal_router',  # НОВЫЙ
    'referral_router'  # НОВЫЙ
]