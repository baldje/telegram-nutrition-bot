# app/utils/callbacks.py
"""
Централизованное хранение всех callback_data
"""

# Юридические callback'и
LEGAL_CALLBACKS = {
    'SHOW_PRIVACY': 'show_privacy',
    'SHOW_OFFER': 'show_offer',
    'ACCEPT_TERMS': 'accept_terms',
    'DECLINE_TERMS': 'decline_terms',
    'SHOW_DOCUMENTS': 'show_documents',
}

# Реферальные callback'и
REFERRAL_CALLBACKS = {
    'SHOW_REFERRAL': 'show_referral',
    'REFERRAL_STATS': 'referral_stats',
    'MY_DISCOUNT': 'my_discount',
    'REFERRAL_RULES': 'referral_rules',
    'ACTIVATE_REFERRAL': 'activate_referral',
    'COPY_REF_PREFIX': 'copy_ref_',  # + код
    'HOW_TO_INCREASE': 'how_to_increase_discount',
    'PAY_WITH_DISCOUNT': 'pay_with_discount',
}

# Платежные callback'и
PAYMENT_CALLBACKS = {
    'TARIFF_MONTH': 'tariff_month',
    'TARIFF_3MONTHS': 'tariff_3months',
    'TARIFF_YEAR': 'tariff_year',
    'PREMIUM_INFO': 'premium_info',
    'CHECK_PAYMENT': 'check_payment',
    'CANCEL_PAYMENT': 'cancel_payment',
}

# Навигационные callback'и
NAVIGATION_CALLBACKS = {
    'BACK_TO_MAIN': 'back_to_main',
}