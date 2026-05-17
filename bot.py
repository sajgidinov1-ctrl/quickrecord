“””
QuickRecord — Бот для записи клиентов
Оплата: перевод на карту Альфа-банк
“””

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
ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
import os

# ============================================================

BOT_TOKEN = os.getenv(“BOT_TOKEN”, “8674542784:AAE7VJ6DqkIMKf9Flsx9TL-qJ4vmZMIf6no”)
ADMIN_CHAT_ID = int(os.getenv(“ADMIN_CHAT_ID”, “8235415794”))

BUSINESS_NAME = “QuickRecord”
BUSINESS_EMOJI = “📅”

# Реквизиты для оплаты

CARD_NUMBER = “2200 1513 5705 2740”
PHONE_NUMBER = “8 993 142-27-07”
CARD_HOLDER = “Динислам Сайгидинов”
BANK_NAME = “Альфа-Банк”

SERVICES = {
“Стрижка”: 1500,
“Стрижка + борода”: 2000,
“Борода”: 800,
“Окрашивание”: 3500,
“Маникюр”: 1200,
“Массаж (60 мин)”: 2500,
}

WORK_HOURS = [
“09:00”, “10:00”, “11:00”, “12:00”,
“13:00”, “14:00”, “15:00”, “16:00”,
“17:00”, “18:00”, “19:00”, “20:00”
]

# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(**name**)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class BookingStates(StatesGroup):
choosing_service = State()
choosing_date = State()
choosing_time = State()
entering_name = State()
entering_phone = State()
confirming = State()
waiting_payment = State()

def services_keyboard():
buttons = []
for service, price in SERVICES.items():
buttons.append([InlineKeyboardButton(
text=f”{service} — {price} руб”,
callback_data=f”svc:{service}:{price}”
)])
return InlineKeyboardMarkup(inline_keyboard=buttons)

def dates_keyboard():
buttons = []
today = datetime.now()
row = []
for i in range(7):
day = today + timedelta(days=i)
label = “Сегодня” if i == 0 else (“Завтра” if i == 1 else day.strftime(”%d.%m”))
row.append(InlineKeyboardButton(
text=label, callback_data=f”date:{day.strftime(’%Y-%m-%d’)}”
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
row.append(InlineKeyboardButton(text=time, callback_data=f”time:{time}”))
if len(row) == 3:
buttons.append(row)
row = []
if row:
buttons.append(row)
return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_keyboard():
return InlineKeyboardMarkup(inline_keyboard=[
[InlineKeyboardButton(text=“✅ Подтвердить и перейти к оплате”, callback_data=“confirm_pay”)],
[InlineKeyboardButton(text=“❌ Отменить”, callback_data=“cancel”)],
])

def paid_keyboard():
return InlineKeyboardMarkup(inline_keyboard=[
[InlineKeyboardButton(text=“✅ Я оплатил — отправить чек”, callback_data=“paid”)],
[InlineKeyboardButton(text=“❌ Отменить запись”, callback_data=“cancel”)],
])

def phone_keyboard():
return ReplyKeyboardMarkup(
keyboard=[[KeyboardButton(text=“📱 Отправить мой номер”, request_contact=True)]],
resize_keyboard=True, one_time_keyboard=True
)

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
await state.clear()
await message.answer(
f”{BUSINESS_EMOJI} *QuickRecord* — быстрая запись к мастеру\n\n”
“Привет! Выбери услугу, и я запишу тебя за 1 минуту 👇”,
parse_mode=“Markdown”,
reply_markup=services_keyboard()
)
await state.set_state(BookingStates.choosing_service)

@dp.callback_query(F.data.startswith(“svc:”))
async def choose_service(callback: types.CallbackQuery, state: FSMContext):
parts = callback.data.split(”:”)
service, price = parts[1], int(parts[2])
await state.update_data(service=service, price=price)
await callback.message.edit_text(
f”✅ Услуга: *{service}* — {price} руб\n\nВыбери дату 📅”,
parse_mode=“Markdown”, reply_markup=dates_keyboard()
)
await state.set_state(BookingStates.choosing_date)
await callback.answer()

@dp.callback_query(F.data.startswith(“date:”))
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
date_str = callback.data.split(”:”)[1]
date_display = datetime.strptime(date_str, “%Y-%m-%d”).strftime(”%d.%m.%Y”)
await state.update_data(date=date_str, date_display=date_display)
await callback.message.edit_text(
f”✅ Дата: *{date_display}*\n\nВыбери время ⏰”,
parse_mode=“Markdown”, reply_markup=times_keyboard()
)
await state.set_state(BookingStates.choosing_time)
await callback.answer()

@dp.callback_query(F.data.startswith(“time:”))
async def choose_time(callback: types.CallbackQuery, state: FSMContext):
time_str = callback.data.split(”:”)[1]
await state.update_data(time=time_str)
await callback.message.edit_text(
f”✅ Время: *{time_str}*\n\nКак тебя зовут? 👇”,
parse_mode=“Markdown”
)
await state.set_state(BookingStates.entering_name)
await callback.answer()

@dp.message(BookingStates.entering_name)
async def enter_name(message: types.Message, state: FSMContext):
name = message.text.strip()
if len(name) < 2:
await message.answer(“Пожалуйста, введи настоящее имя 😊”)
return
await state.update_data(name=name)
await message.answer(
f”Отлично, *{name}*! 👋\n\nПоделись номером телефона:”,
parse_mode=“Markdown”, reply_markup=phone_keyboard()
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
f”📋 *Детали записи:*\n\n”
f”💆 {data[‘service’]}\n”
f”📅 {data[‘date_display’]}\n”
f”⏰ {data[‘time’]}\n”
f”👤 {data[‘name’]}\n”
f”📱 {data[‘phone’]}\n”
f”💰 {data[‘price’]} руб\n\n”
“Всё верно?”,
parse_mode=“Markdown”,
reply_markup=confirm_keyboard()
)
await state.set_state(BookingStates.confirming)

@dp.callback_query(F.data == “confirm_pay”)
async def show_payment(callback: types.CallbackQuery, state: FSMContext):
data = await state.get_data()
await callback.message.delete()
await callback.message.answer(
f”💳 *Оплата заказа*\n\n”
f”Сумма: *{data[‘price’]} руб*\n\n”
f”Переведи на карту или по СБП:\n\n”
f”🏦 Банк: *{BANK_NAME}*\n”
f”💳 Карта: `{CARD_NUMBER}`\n”
f”📱 Телефон (СБП): `{PHONE_NUMBER}`\n”
f”👤 Получатель: *{CARD_HOLDER}*\n\n”
f”После оплаты нажми кнопку ниже 👇”,
parse_mode=“Markdown”,
reply_markup=paid_keyboard()
)
await state.set_state(BookingStates.waiting_payment)
await callback.answer()

@dp.callback_query(F.data == “paid”)
async def payment_confirmed(callback: types.CallbackQuery, state: FSMContext):
data = await state.get_data()
user = callback.from_user

```
await callback.message.edit_text(
    f"📸 Отправь скриншот чека оплаты — это подтвердит твою запись!",
    parse_mode="Markdown"
)
await callback.answer()
```

@dp.message(BookingStates.waiting_payment, F.photo)
async def receive_receipt(message: types.Message, state: FSMContext):
data = await state.get_data()
user = message.from_user

```
# Клиенту
await message.answer(
    f"🎉 *Запись подтверждена!*\n\n"
    f"✅ {data['service']}\n"
    f"📅 {data['date_display']} в {data['time']}\n"
    f"🏢 {BUSINESS_NAME}\n\n"
    f"Ждём тебя! По вопросам — пиши напрямую.",
    parse_mode="Markdown",
    reply_markup=ReplyKeyboardRemove()
)

# Администратору — пересылаем чек
try:
    await bot.send_message(
        ADMIN_CHAT_ID,
        f"🔔 *НОВАЯ ЗАПИСЬ + ЧЕК ОБ ОПЛАТЕ!*\n\n"
        f"💆 {data['service']}\n"
        f"📅 {data['date_display']} в {data['time']}\n"
        f"👤 {data['name']}\n"
        f"📱 {data['phone']}\n"
        f"💰 {data['price']} руб\n"
        f"🆔 @{user.username or 'нет'} (ID: {user.id})",
        parse_mode="Markdown"
    )
    await bot.forward_message(
        chat_id=ADMIN_CHAT_ID,
        from_chat_id=message.chat.id,
        message_id=message.message_id
    )
except Exception as e:
    logger.error(f"Ошибка: {e}")

await state.clear()
```

@dp.callback_query(F.data == “cancel”)
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
await state.clear()
await callback.message.edit_text(“❌ Отменено. Напиши /start чтобы начать заново.”)
await callback.answer()

async def main():
logger.info(“🚀 QuickRecord запущен!”)
await dp.start_polling(bot)

if **name** == “**main**”:
asyncio.run(main())
