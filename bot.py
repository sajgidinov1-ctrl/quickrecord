"""
QuickRecord — Бот для записи клиентов
Версия для Render.com (polling)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8674542784:AAE7VJ6DqkIMKf9Flsx9TL-qJ4vmZMIf6no")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "8235415794"))

BUSINESS_NAME = "QuickRecord"
BUSINESS_EMOJI = "📅"

SERVICES = {
    "Стрижка": 100,
    "Стрижка + борода": 150,
    "Борода": 80,
    "Окрашивание": 250,
    "Маникюр": 120,
    "Массаж (60 мин)": 200,
}

WORK_HOURS = [
    "09:00", "10:00", "11:00", "12:00",
    "13:00", "14:00", "15:00", "16:00",
    "17:00", "18:00", "19:00", "20:00"
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    confirming = State()
    paying = State()


def services_keyboard():
    buttons = []
    for service, price in SERVICES.items():
        buttons.append([InlineKeyboardButton(
            text=f"{service} — {price} ⭐",
            callback_data=f"svc:{service}:{price}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def dates_keyboard():
    buttons = []
    today = datetime.now()
    row = []
    for i in range(7):
        day = today + timedelta(days=i)
        label = "Сегодня" if i == 0 else ("Завтра" if i == 1 else day.strftime("%d.%m"))
        row.append(InlineKeyboardButton(
            text=label, callback_data=f"date:{day.strftime('%Y-%m-%d')}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def times_keyboard():
    buttons = []
    row = []
    for time in WORK_HOURS:
        row.append(InlineKeyboardButton(text=time, callback_data=f"time:{time}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплатить и записаться", callback_data="confirm_pay")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel")],
    ])


def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"{BUSINESS_EMOJI} *QuickRecord* — быстрая запись к мастеру\n\nПривет! Выбери услугу 👇",
        parse_mode="Markdown", reply_markup=services_keyboard()
    )
    await state.set_state(BookingStates.choosing_service)


@dp.callback_query(F.data.startswith("svc:"))
async def choose_service(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    service, price = parts[1], int(parts[2])
    await state.update_data(service=service, price=price)
    await callback.message.edit_text(
        f"✅ Услуга: *{service}* — {price} ⭐\n\nВыбери дату 📅",
        parse_mode="Markdown", reply_markup=dates_keyboard()
    )
    await state.set_state(BookingStates.choosing_date)
    await callback.answer()


@dp.callback_query(F.data.startswith("date:"))
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":")[1]
    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    await state.update_data(date=date_str, date_display=date_display)
    await callback.message.edit_text(
        f"✅ Дата: *{date_display}*\n\nВыбери время ⏰",
        parse_mode="Markdown", reply_markup=times_keyboard()
    )
    await state.set_state(BookingStates.choosing_time)
    await callback.answer()


@dp.callback_query(F.data.startswith("time:"))
async def choose_time(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.split(":")[1]
    await state.update_data(time=time_str)
    await callback.message.edit_text(
        f"✅ Время: *{time_str}*\n\nКак тебя зовут? 👇",
        parse_mode="Markdown"
    )
    await state.set_state(BookingStates.entering_name)
    await callback.answer()


@dp.message(BookingStates.entering_name)
async def enter_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Пожалуйста, введи настоящее имя 😊")
        return
    await state.update_data(name=name)
    await message.answer(
        f"Отлично, *{name}*! 👋\n\nПоделись номером телефона:",
        parse_mode="Markdown", reply_markup=phone_keyboard()
    )
    await state.set_state(BookingStates.entering_phone)


@dp.message(BookingStates.entering_phone, F.contact)
async def enter_phone_contact(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await show_confirmation(message, state)


@dp.message(BookingStates.entering_phone, F.text)
async def enter_phone_text(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await show_confirmation(message, state)


async def show_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await message.answer(
        f"📋 *Детали записи:*\n\n"
        f"💆 {data['service']}\n📅 {data['date_display']}\n⏰ {data['time']}\n"
        f"👤 {data['name']}\n📱 {data['phone']}\n💰 {data['price']} ⭐\n\n"
        "Всё верно? Нажми *Оплатить*!",
        parse_mode="Markdown", reply_markup=confirm_keyboard()
    )
    await state.set_state(BookingStates.confirming)


@dp.callback_query(F.data == "confirm_pay")
async def send_invoice(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.delete()
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"📅 {data['service']}",
        description=f"{data['date_display']} в {data['time']} | {data['name']}",
        payload=f"booking_{callback.from_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label=data['service'], amount=data['price'])],
    )
    await state.set_state(BookingStates.paying)
    await callback.answer()


@dp.callback_query(F.data == "cancel")
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Отменено. Напиши /start чтобы начать заново.")
    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def payment_success(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = message.from_user
    await message.answer(
        f"🎉 *Запись подтверждена!*\n\n✅ {data['service']}\n"
        f"📅 {data['date_display']} в {data['time']}\n🏢 {BUSINESS_NAME}\n\nЖдём тебя!",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    try:
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"🔔 *НОВАЯ ЗАПИСЬ!*\n\n💆 {data['service']}\n📅 {data['date_display']} в {data['time']}\n"
            f"👤 {data['name']}\n📱 {data['phone']}\n💰 {data['price']} ⭐\n"
            f"🆔 @{user.username or 'нет'} (ID: {user.id})",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
    await state.clear()


async def main():
    logger.info("🚀 QuickRecord запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
