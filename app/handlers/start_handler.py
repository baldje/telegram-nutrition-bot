from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
import logging
from datetime import datetime, timedelta

from app.utils.states import OnboardingStates
from app.utils.navigation import Navigation
from app.database.crud import UserCRUD, TrainerCRUD

logger = logging.getLogger(__name__)
start_router = Router()


def get_goal_keyboard():
    """Клавиатура для выбора цели"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Похудение")],
            [KeyboardButton(text="Набор массы")],
            [KeyboardButton(text="Поддержание")],
            [KeyboardButton(text="Рельеф")],
            [KeyboardButton(text="Здоровье")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


@start_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db=None):
    """Главное меню с обработкой редиректов от Т-Банка, реферальных кодов и приглашений тренера"""
    try:
        await state.clear()

        # Проверяем параметры (редирект от Т-Банка, рефералка или приглашение тренера)
        args = message.text.split()

        if len(args) > 1:
            param = args[1]
            logger.info(f"📱 Параметр start: {param} от пользователя {message.from_user.id}")

            # Проверяем, это редирект от Т-Банка?
            if param.startswith('payment_success_'):
                # Успешная оплата
                order_id = param.replace('payment_success_', '')
                await message.answer(
                    "✅ *Оплата прошла успешно!*\n\n"
                    "Спасибо за покупку! Ваша подписка активируется через несколько секунд.\n"
                    "Теперь вам доступны все премиум-функции.",
                    parse_mode="HTML"
                )
                # Проверим статус платежа
                await check_payment_by_order(message, state, db, order_id, success=True)
                return

            elif param.startswith('payment_failed_'):
                # Неуспешная оплата
                order_id = param.replace('payment_failed_', '')
                await message.answer(
                    "❌ *Оплата не прошла*\n\n"
                    "Попробуйте еще раз или выберите другой способ оплаты.\n"
                    "Если деньги списались, но подписка не активировалась - напишите в поддержку.",
                    parse_mode="HTML",
                    reply_markup=Navigation.get_premium_inline_menu()
                )
                await check_payment_by_order(message, state, db, order_id, success=False)
                return

            elif param.startswith('ref_'):
                # Реферальный код
                referral_code = param[4:]  # убираем 'ref_'
                logger.info(f"✅ Извлечен реферальный код: {referral_code}")
                await state.update_data(referral_code=referral_code)

            elif param.startswith('trainer_'):
                # Ссылка-приглашение от тренера
                try:
                    trainer_id = int(param.split('_')[1])
                    await state.update_data(invite_trainer_id=trainer_id)
                    logger.info(f"📨 Пользователь перешел по ссылке тренера {trainer_id}")
                except:
                    logger.warning(f"❌ Неверный формат trainer_ параметра: {param}")

        # Проверяем, есть ли пользователь в БД
        user = None
        if db:
            user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)

        if not user:
            # Новый пользователь
            await message.answer(
                "Привет! Я бот Лизы — помогу тебе с питанием, фото-анализом и тренировками.\n"
                "3 дня теста бесплатно. Начнём?",
                reply_markup=Navigation.get_onboarding_start_keyboard()
            )
        else:
            # Существующий пользователь — показываем меню в зависимости от роли
            await message.answer(
                f"👋 *С возвращением!*\n\n"
                f"Выбери раздел:",
                parse_mode="HTML",
                reply_markup=Navigation.get_main_menu(user.role if user else 'user')
            )

        logger.info(f"Пользователь {message.from_user.id} запустил бота")

    except Exception as e:
        logger.error(f"Ошибка в cmd_start: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


async def check_payment_by_order(message: Message, state: FSMContext, db, order_id: str, success: bool):
    """Проверка платежа по order_id после редиректа"""
    try:
        from app.handlers.payments import TinkoffPaymentService, TARIFFS

        tinkoff_service = TinkoffPaymentService()

        # В тестовом режиме просто показываем сообщение
        if success:
            # Активируем тестовую подписку
            if db and hasattr(db, 'session'):
                try:
                    user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
                    if user:
                        # Активируем тестовую подписку на 7 дней
                        from datetime import datetime, timedelta

                        if user.subscription_until and user.subscription_until > datetime.utcnow():
                            # Если уже есть активная подписка, продлеваем
                            user.subscription_until += timedelta(days=7)
                        else:
                            # Новая подписка
                            user.subscription_until = datetime.utcnow() + timedelta(days=7)

                        user.subscription_status = "active"
                        await db.session.commit()

                        await message.answer(
                            "🎉 *Подписка активирована!*\n\n"
                            f"✅ Тестовый доступ на 7 дней\n"
                            f"📅 Действует до: {user.subscription_until.strftime('%d.%m.%Y')}\n\n"
                            "Теперь вам доступны все функции бота!",
                            parse_mode="HTML",
                            reply_markup=Navigation.get_main_menu(user.role if user else 'user')
                        )
                        return
                except Exception as e:
                    logger.error(f"Ошибка активации подписки: {e}")

            # Если не удалось активировать через БД
            await message.answer(
                "🎉 *Оплата прошла успешно!*\n\n"
                "Подписка будет активирована в ближайшее время.\n"
                "Если этого не произошло - нажмите /check_payment",
                parse_mode="HTML",
                reply_markup=Navigation.get_main_menu()
            )
    except Exception as e:
        logger.error(f"Ошибка проверки платежа: {e}")


@start_router.message(F.text == "🔙 В главное меню")
async def back_to_main(message: Message, state: FSMContext, db=None):
    """Возврат в главное меню"""
    await state.clear()

    # Получаем роль пользователя для правильного меню
    user_role = 'user'
    if db:
        try:
            user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
            if user:
                user_role = user.role
        except:
            pass

    await message.answer(
        "Главное меню:",
        reply_markup=Navigation.get_main_menu(user_role)
    )


@start_router.message(F.text == "❌ Отменить действие")
async def cancel_action(message: Message, state: FSMContext, db=None):
    """Отмена текущего действия"""
    await state.clear()

    # Получаем роль пользователя для правильного меню
    user_role = 'user'
    if db:
        try:
            user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
            if user:
                user_role = user.role
        except:
            pass

    await message.answer(
        "✅ Действие отменено.\n"
        "Выбери, что хочешь сделать:",
        reply_markup=Navigation.get_main_menu(user_role)
    )


@start_router.message(F.text == "✅ Да, начать")
async def start_trial(message: Message, state: FSMContext, db=None):
    """Начало триального периода"""
    try:
        await message.answer(
            "🎉 Отлично! Давай создадим твой персональный план.\n\n"
            "🎯 <b>Какую цель ты преследуешь?</b>",
            parse_mode="HTML",
            reply_markup=get_goal_keyboard()
        )

        # Устанавливаем состояние - выбор цели
        await state.set_state(OnboardingStates.waiting_goal)
        logger.info(f"Пользователь {message.from_user.id} начал онбординг с выбора цели")

    except Exception as e:
        logger.error(f"Ошибка в start_trial: {e}")
        await message.answer("❌ Ошибка при запуске теста")


@start_router.message(F.text == "ℹ️ Что умеет бот")
async def bot_features(message: Message):
    """Описание возможностей бота"""
    features_text = (
        "🤖 <b>Что я умею:</b>\n\n"
        "🍽 <b>Питание</b>\n"
        "• Персональные планы питания\n"
        "• Анализ фото еды\n"
        "• Советы по КБЖУ\n"
        "• Списки покупок\n\n"

        "💪 <b>Тренировки</b>\n"
        "• Планы тренировок\n"
        "• Отслеживание прогресса\n"
        "• Медали и достижения\n"
        "• Еженедельные челленджи\n\n"

        "🏆 <b>Мотивация</b>\n"
        "• Рейтинги участников\n"
        "• Статусы и уровни\n"
        "• Напоминания\n\n"

        "🎯 <b>Начни с 3-дневного теста бесплатно!</b>"
    )

    await message.answer(features_text, parse_mode="HTML", reply_markup=Navigation.get_back_button())


@start_router.message(F.text == "❌ Не сейчас")
async def not_now(message: Message, db=None):
    """Пользователь не хочет начинать сейчас"""
    # Получаем роль пользователя для правильного меню
    user_role = 'user'
    if db:
        try:
            user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
            if user:
                user_role = user.role
        except:
            pass

    await message.answer(
        "Хорошо! Если захочешь начать, просто напиши /start",
        reply_markup=Navigation.get_main_menu(user_role)
    )


@start_router.message(F.text == "🍽 Питание")
async def nutrition_menu(message: Message):
    """Меню питания"""
    await message.answer(
        "🍽 *Раздел питания*\n\n"
        "Выбери действие:",
        parse_mode="HTML",
        reply_markup=Navigation.get_nutrition_menu()
    )


@start_router.message(F.text == "💎 Премиум")
async def premium_menu(message: Message, db=None):
    """Меню премиум"""
    discount = 0
    role_text = ""

    if db:
        try:
            user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
            if user:
                discount = user.discount_percent or 0
                if user.role == 'trainer':
                    role_text = "\n\n👨‍🏫 *Вы наставник!* У вас есть доступ к панели управления."
        except:
            pass

    await message.answer(
        f"💎 *Премиум подписка*\n\n"
        f"Получи доступ к:\n"
        f"• 📸 Анализу фото еды\n"
        f"• 📊 Расширенной статистике\n"
        f"• ♾️ Безлимитным запросам{role_text}\n\n"
        f"Стоимость от 299 ₽/мес",
        parse_mode="HTML",
        reply_markup=Navigation.get_premium_inline_menu(discount)
    )


@start_router.message(F.text == "❓ Помощь")
async def help_menu(message: Message):
    """Меню помощи"""
    await message.answer(
        "❓ *Помощь*\n\n"
        "Выбери раздел:",
        parse_mode="HTML",
        reply_markup=Navigation.get_help_menu()
    )


@start_router.message(F.text == "📋 Команды бота")
async def bot_commands(message: Message):
    """Список команд"""
    await message.answer(
        "📋 *Основные команды:*\n\n"
        "/start - Главное меню\n"
        "/subscribe - Оформить подписку\n"
        "/analyze - Анализ фото еды\n"
        "/premium - Премиум функции\n"
        "/status - Статус подписки\n"
        "/cancel - Отменить действие",
        parse_mode="HTML",
        reply_markup=Navigation.get_back_button()
    )


@start_router.message(F.text == "📞 Связаться с поддержкой")
async def support(message: Message):
    """Поддержка"""
    await message.answer(
        "📞 *Служба поддержки*\n\n"
        "По всем вопросам пишите:\n"
        "✉️ @baldje\n\n"
        "Среднее время ответа: до 24 часов",
        parse_mode="HTML",
        reply_markup=Navigation.get_back_button()
    )


@start_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, db=None):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    if current_state:
        logger.info(f"🔄 Отмена состояния {current_state} для пользователя {message.from_user.id}")
        await state.clear()

        # Получаем роль пользователя для правильного меню
        user_role = 'user'
        if db:
            try:
                user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
                if user:
                    user_role = user.role
            except:
                pass

        await message.answer(
            "❌ Действие отменено.\n"
            "Выбери, что хочешь сделать:",
            reply_markup=Navigation.get_main_menu(user_role)
        )
    else:
        # Получаем роль пользователя для правильного меню
        user_role = 'user'
        if db:
            try:
                user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)
                if user:
                    user_role = user.role
            except:
                pass

        await message.answer(
            "Нет активного действия для отмены.",
            reply_markup=Navigation.get_main_menu(user_role)
        )


@start_router.message(Command("status"))
async def cmd_status(message: Message, db=None):
    """Показать статус подписки"""
    if not db:
        await message.answer("❌ Ошибка: нет подключения к базе данных")
        return

    try:
        user = await UserCRUD.get_by_telegram_id(db.session, message.from_user.id)

        if not user:
            await message.answer(
                "❌ Пользователь не найден. Напишите /start для регистрации.",
                reply_markup=Navigation.get_main_menu()
            )
            return

        # Проверяем статус подписки
        now = datetime.utcnow()

        status_text = "❌ Нет активной подписки"
        days_left = 0

        if user.subscription_until and user.subscription_until > now:
            days_left = (user.subscription_until - now).days
            status_text = f"⭐ Премиум подписка (осталось {days_left} дн.)"
        elif user.trial_started_at:
            trial_end = user.trial_started_at + timedelta(days=3)
            if now < trial_end:
                days_left = (trial_end - now).days
                status_text = f"🆓 Бесплатный триал (осталось {days_left} дн.)"

        # Формируем ответ
        response = f"""
📊 **ТВОЯ СТАТИСТИКА**

👤 **Пользователь:** {user.full_name or user.username or 'Неизвестно'}
📅 **Зарегистрирован:** {user.created_at.strftime('%d.%m.%Y')}
📸 **Проанализировано фото:** {user.photo_analyzes_count or 0}

🔐 **СТАТУС ПОДПИСКИ:**
{status_text}

💰 **БАЛАНС:** {user.balance or 0} ₽
🎁 **СКИДКА:** {user.discount_percent or 0}%

❓ Хочешь оформить подписку? /subscribe
        """

        await message.answer(response, parse_mode="HTML", reply_markup=Navigation.get_main_menu(user.role))

    except Exception as e:
        logger.error(f"Ошибка в /status: {e}")
        await message.answer("❌ Произошла ошибка при получении статуса")


@start_router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext, db=None):
    """Возврат в главное меню (из inline)"""
    await state.clear()

    # Получаем роль пользователя для правильного меню
    user_role = 'user'
    if db:
        try:
            user = await UserCRUD.get_by_telegram_id(db.session, callback.from_user.id)
            if user:
                user_role = user.role
        except:
            pass

    await callback.message.delete()
    await callback.message.answer(
        "Главное меню:",
        reply_markup=Navigation.get_main_menu(user_role)
    )
    await callback.answer()