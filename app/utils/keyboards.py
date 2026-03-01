from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

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

def get_gender_keyboard():
    """Клавиатура для выбора пола"""
    buttons = [
        [KeyboardButton(text="Мужской")],
        [KeyboardButton(text="Женский")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_yes_no_keyboard():
    """Клавиатура для ответа да/нет"""
    buttons = [
        [KeyboardButton(text="Да")],
        [KeyboardButton(text="Нет")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_activity_keyboard():
    """Клавиатура для уровня активности"""
    buttons = [
        [KeyboardButton(text="Низкая")],
        [KeyboardButton(text="Средняя")],
        [KeyboardButton(text="Высокая")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)