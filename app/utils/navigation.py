# app/utils/navigation.py
"""
Централизованная навигация по боту
Все меню и кнопки в одном месте
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


class Navigation:
    """Класс со всеми меню бота"""

    @staticmethod
    def get_main_menu() -> ReplyKeyboardMarkup:
        """Главное меню"""
        builder = ReplyKeyboardBuilder()

        builder.row(
            KeyboardButton(text="🍽 Питание"),
            KeyboardButton(text="💎 Премиум"),
            width=2
        )
        builder.row(
            KeyboardButton(text="🎁 Рефералка"),
            KeyboardButton(text="💰 Моя скидка"),
            width=2
        )
        builder.row(
            KeyboardButton(text="❓ Помощь"),
            KeyboardButton(text="🔐 Документы"),
            width=2
        )

        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def get_nutrition_menu() -> ReplyKeyboardMarkup:
        """Меню питания"""
        builder = ReplyKeyboardBuilder()

        builder.row(
            KeyboardButton(text="📸 Анализ фото"),
            KeyboardButton(text="📝 Описать еду"),
            width=2
        )
        builder.row(
            KeyboardButton(text="🔙 В главное меню"),
            width=1
        )

        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def get_premium_inline_menu(discount: int = 0) -> InlineKeyboardMarkup:
        """Inline меню для премиум с учетом скидки"""
        builder = InlineKeyboardBuilder()

        # Тестовый тариф (всегда показываем)
        #builder.row(
        #     InlineKeyboardButton(text="🧪 Тестовый доступ 7 дней - 1 ₽",
        #                          callback_data="tariff_test_week"),
        #     width=1
        #)

        # Расчет цен со скидкой для остальных тарифов
        month_price = 299
        three_months_price = 799
        year_price = 2990

        if discount > 0:
            month_price = int(month_price * (100 - discount) / 100)
            three_months_price = int(three_months_price * (100 - discount) / 100)
            year_price = int(year_price * (100 - discount) / 100)

        discount_text = f" (скидка {discount}%)" if discount > 0 else ""

        builder.row(
            InlineKeyboardButton(text=f"📅 1 месяц - {month_price} ₽{discount_text}",
                                 callback_data="tariff_month"),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text=f"📊 3 месяца - {three_months_price} ₽{discount_text}",
                                 callback_data="tariff_3months"),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text=f"🏆 1 год - {year_price} ₽{discount_text}",
                                 callback_data="tariff_year"),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text="❓ Что входит в премиум", callback_data="premium_info"),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text="🎁 Реферальная программа", callback_data="referral_info"),
            InlineKeyboardButton(text="💰 Моя скидка", callback_data="my_discount"),
            width=2
        )
        builder.row(
            InlineKeyboardButton(text="💳 Оплатить со скидкой", callback_data="pay_with_discount"),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_main"),
            width=1
        )

        return builder.as_markup()

    @staticmethod
    def get_payment_keyboard(payment_url: str, discount: int = 0) -> InlineKeyboardMarkup:
        """Клавиатура для оплаты с учетом скидки"""
        builder = InlineKeyboardBuilder()

        discount_text = f" (скидка {discount}%)" if discount > 0 else ""

        builder.row(
            InlineKeyboardButton(text=f"💳 Перейти к оплате{discount_text}", url=payment_url),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text="🔄 Проверить статус", callback_data="check_payment"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_payment"),
            width=2
        )
        builder.row(
            InlineKeyboardButton(text="🎁 Активировать реферальный код", callback_data="activate_referral"),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text="◀️ В главное меню", callback_data="back_to_main"),
            width=1
        )

        return builder.as_markup()

    @staticmethod
    def get_help_menu() -> ReplyKeyboardMarkup:
        """Меню помощи"""
        builder = ReplyKeyboardBuilder()

        builder.row(
            KeyboardButton(text="📋 Команды бота"),
            KeyboardButton(text="📞 Связаться с поддержкой"),
            width=2
        )
        builder.row(
            KeyboardButton(text="🔐 Политика конфиденциальности"),
            KeyboardButton(text="📄 Публичная оферта"),
            width=2
        )
        builder.row(
            KeyboardButton(text="🔙 В главное меню"),
            width=1
        )

        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def get_documents_menu() -> ReplyKeyboardMarkup:
        """Меню документов"""
        builder = ReplyKeyboardBuilder()

        builder.row(
            KeyboardButton(text="🔐 Политика конфиденциальности"),
            KeyboardButton(text="📄 Публичная оферта"),
            width=2
        )
        builder.row(
            KeyboardButton(text="🔙 В главное меню"),
            width=1
        )

        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def get_back_button() -> ReplyKeyboardMarkup:
        """Кнопка возврата"""
        builder = ReplyKeyboardBuilder()
        builder.button(text="🔙 В главное меню")
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def get_cancel_keyboard() -> ReplyKeyboardMarkup:
        """Кнопка отмены для онбординга"""
        builder = ReplyKeyboardBuilder()
        builder.button(text="❌ Отменить действие")
        builder.button(text="🔙 В главное меню")
        builder.adjust(1)
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def get_onboarding_start_keyboard() -> ReplyKeyboardMarkup:
        """Клавиатура для начала онбординга"""
        builder = ReplyKeyboardBuilder()
        builder.button(text="✅ Да, начать")
        builder.button(text="ℹ️ Что умеет бот")
        builder.button(text="🔐 Согласие на обработку данных")
        builder.button(text="❌ Не сейчас")
        builder.adjust(2, 1, 1)
        return builder.as_markup(resize_keyboard=True)

    # ===== ЮРИДИЧЕСКИЕ КЛАВИАТУРЫ =====

    @staticmethod
    def get_legal_inline_keyboard() -> InlineKeyboardMarkup:
        """Инлайн клавиатура для юридических документов"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(text="🔐 Политика конфиденциальности", callback_data="show_privacy"),
            InlineKeyboardButton(text="📄 Публичная оферта", callback_data="show_offer"),
            width=2
        )
        builder.row(
            InlineKeyboardButton(text="✅ Принимаю условия", callback_data="accept_terms"),
            InlineKeyboardButton(text="❌ Отказаться", callback_data="decline_terms"),
            width=2
        )

        return builder.as_markup()

    @staticmethod
    def get_accept_only_keyboard() -> InlineKeyboardMarkup:
        """Упрощенная клавиатура только с кнопкой принятия"""
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Принимаю условия", callback_data="accept_terms")
        return builder.as_markup()

    @staticmethod
    def get_consent_reminder_keyboard() -> InlineKeyboardMarkup:
        """Клавиатура для напоминания о согласии"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔐 Прочитать документы", callback_data="show_documents"),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text="✅ Принять условия", callback_data="accept_terms"),
            width=1
        )
        return builder.as_markup()

    # ===== РЕФЕРАЛЬНЫЕ КЛАВИАТУРЫ =====

    @staticmethod
    def get_referral_inline_keyboard(referral_code: str) -> InlineKeyboardMarkup:
        """Инлайн клавиатура для реферальной программы"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(text="📋 Скопировать ссылку", callback_data=f"copy_ref_{referral_code}"),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text="📊 Статистика", callback_data="referral_stats"),
            InlineKeyboardButton(text="💰 Моя скидка", callback_data="my_discount"),
            width=2
        )
        builder.row(
            InlineKeyboardButton(text="📖 Правила программы", callback_data="referral_rules"),
            InlineKeyboardButton(text="🎁 Активировать код", callback_data="activate_referral"),
            width=2
        )

        return builder.as_markup()

    @staticmethod
    def get_discount_info_keyboard() -> InlineKeyboardMarkup:
        """Инлайн клавиатура для информации о скидке"""
        builder = InlineKeyboardBuilder()

        builder.row(
            InlineKeyboardButton(text="🎁 Пригласить друзей", callback_data="show_referral"),
            width=1
        )
        builder.row(
            InlineKeyboardButton(text="💳 Оплатить со скидкой", callback_data="pay_with_discount"),
            InlineKeyboardButton(text="📊 Как увеличить скидку", callback_data="how_to_increase_discount"),
            width=2
        )

        return builder.as_markup()
