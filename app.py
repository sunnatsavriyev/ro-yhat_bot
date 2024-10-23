# bot/management/commands/runbot.py

import os
import json
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from datetime import datetime
from aiogram import types
from aiogram.utils.exceptions import BotBlocked
# Define the path for the registered users file
REGISTERED_USERS_FILE = 'registered_users.json'

def load_registered_users():
    """Load registered users from a JSON file."""
    if os.path.exists(REGISTERED_USERS_FILE):
        with open(REGISTERED_USERS_FILE, 'r', encoding='utf-8') as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                return []
    return []

def save_registered_users():
    """Save registered users to a JSON file."""
    with open(REGISTERED_USERS_FILE, 'w', encoding='utf-8') as file:
        json.dump(registered_users, file, ensure_ascii=False, indent=4)

# Load environment variables from .env
load_dotenv()

# Bot and Dispatcher setup
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))  # Admin ID
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Define FSM States
class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone_number = State()
    waiting_for_date = State()
    waiting_for_worker_count = State()

# Load registered users
registered_users = load_registered_users()  # List of dicts: [{user_id, first_name, last_name, phone_number}, ...]
attending_users = []   # List of dicts: [{user_id, first_name, last_name}, ...]
required_worker_count = 0  # Required number of workers
current_date = ""  # Date for which workers are needed

# Create Keyboards
# Admin Keyboard
admin_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
admin_button_request = types.KeyboardButton("Ishchi kerak")
admin_button_list = types.KeyboardButton("Ishchilar ro'yhati")
admin_keyboard.add(admin_button_request, admin_button_list)

# User Keyboard
user_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
user_button_list = types.KeyboardButton("Ishchilar ro'yhati")
# Button to share contact
user_button_attend = types.KeyboardButton("Men chiqaman", request_contact=False)
user_button_contact = types.KeyboardButton("Bog'lanish uchun telefon raqamimni yuborish", request_contact=True)
user_keyboard.add(user_button_list, user_button_attend, user_button_contact)

# /start command handler
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    # Check if user is already registered
    user = next((user for user in registered_users if user['user_id'] == user_id), None)
    if user and user.get('first_name') and user.get('last_name') and user.get('phone_number'):
        await message.answer("Siz allaqachon ro'yhatdan o'tgansiz!")
    else:
        await message.answer("Ismingiz va familiyangizni kiriting (masalan, Anvar Karimov):")
        await RegistrationStates.waiting_for_full_name.set()

# Handler for full name
@dp.message_handler(state=RegistrationStates.waiting_for_full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    name_parts = full_name.split()

    if len(name_parts) < 2:
        await message.answer("Iltimos, ismingiz va familiyangizni bitta xabar orqali kiriting (masalan, Plonchiyev Pistonchi).")
        return

    first_name = name_parts[0]
    last_name = ' '.join(name_parts[1:])  # Supports multi-part last names

    # Update FSM context
    await state.update_data(first_name=first_name, last_name=last_name)

    # Ask for phone number
    contact_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    contact_button = types.KeyboardButton("Telefon raqamni yuborish", request_contact=True)
    contact_keyboard.add(contact_button)
    await message.answer("Bog'lanish uchun telefon raqamingizni yuboring:", reply_markup=contact_keyboard)
    await RegistrationStates.waiting_for_phone_number.set()

# Handler for phone number
@dp.message_handler(content_types=types.ContentType.CONTACT, state=RegistrationStates.waiting_for_phone_number)
async def process_phone_number(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    contact = message.contact
    phone_number = contact.phone_number

    # Retrieve FSM data
    data = await state.get_data()
    first_name = data.get('first_name')
    last_name = data.get('last_name')

    # Check if the phone number belongs to the user
    if contact.user_id != user_id:
        await message.answer("Iltimos, faqat o'zingizning telefon raqamingizni yuboring.")
        return

    # Update registered_users
    new_user = {
        "user_id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number
    }
    registered_users.append(new_user)
    save_registered_users()  # Save to file

    await message.answer(f"Xush kelibsiz, {first_name} {last_name}!\nTelefon raqamingiz muvaffaqiyatli saqlandi.")

    if user_id != ADMIN_ID:
        # Notify admin about new registration
        await bot.send_message(
            ADMIN_ID,
            f"Yangi foydalanuvchi ro'yhatga olindi:\nIsm: {first_name} {last_name}\nTelefon: {phone_number}",
            reply_markup=admin_keyboard
        )
        # Send user keyboard
        await message.answer("Siz ro'yhatga olindingiz.", reply_markup=user_keyboard)
    else:
        # Admin user
        await message.answer(
            "Admin paneli:\nIshchi kerak tugmasini bosish orqali ishchi so'rashingiz mumkin.",
            reply_markup=admin_keyboard
        )

    # Reset keyboard to default after sharing contact
    await state.finish()

# Handler in case user sends phone number as text
@dp.message_handler(lambda message: message.text and message.text.startswith('+'), state=RegistrationStates.waiting_for_phone_number)
async def process_phone_number_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    phone_number = message.text.strip()

    # Simple validation for phone number
    if not phone_number.startswith('+') or not phone_number[1:].isdigit():
        await message.answer("Iltimos, to'g'ri telefon raqamini kiriting (masalan, +998901234567).")
        return

    # Retrieve FSM data
    data = await state.get_data()
    first_name = data.get('first_name')
    last_name = data.get('last_name')

    # Update registered_users
    new_user = {
        "user_id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number
    }
    registered_users.append(new_user)
    save_registered_users()  # Save to file

    await message.answer(f"Xush kelibsiz, {first_name} {last_name}!\nTelefon raqamingiz muvaffaqiyatli saqlandi.")

    if user_id != ADMIN_ID:
        # Notify admin about new registration
        await bot.send_message(
            ADMIN_ID,
            f"Yangi foydalanuvchi ro'yhatga olindi:\nIsm: {first_name} {last_name}\nTelefon: {phone_number}",
            reply_markup=admin_keyboard
        )
        # Send user keyboard
        await message.answer("Siz ro'yhatga olindingiz.", reply_markup=user_keyboard)
    else:
        # Admin user
        await message.answer(
            "Admin paneli:\nIshchi kerak tugmasini bosish orqali ishchi so'rashingiz mumkin.",
            reply_markup=admin_keyboard
        )

    # Reset keyboard to default after sharing contact
    await state.finish()

# Admin: Request Workers
@dp.message_handler(lambda message: message.text == "Ishchi kerak", user_id=ADMIN_ID)
async def request_workers(message: types.Message):
    await message.answer("Sanani kiriting (YYYY-MM-DD formatida):")
    await RegistrationStates.waiting_for_date.set()

# Handler for date
@dp.message_handler(state=RegistrationStates.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    global current_date
    date_text = message.text.strip()
    try:
        # Validate date format
        datetime_obj = datetime.strptime(date_text, '%Y-%m-%d')
        current_date = date_text
    except ValueError:
        await message.answer("Noto'g'ri format. Iltimos, YYYY-MM-DD formatida sanani kiriting.")
        return

    await message.answer("Ishchi sonini kiriting:")
    await RegistrationStates.waiting_for_worker_count.set()

# Handler for worker count
@dp.message_handler(state=RegistrationStates.waiting_for_worker_count)
async def process_worker_count(message: types.Message, state: FSMContext):
    global required_worker_count, attending_users
    count_text = message.text.strip()
    if count_text.isdigit():
        required_worker_count = int(count_text)
        attending_users = []  # Reset attending users list

        # Notify all users except admin
        for user in registered_users:
            if user['user_id'] != ADMIN_ID:
                markup = user_keyboard  # User keyboard
                await bot.send_message(
                    user['user_id'],
                    f"{current_date} sanasida {required_worker_count} ishchi kerak! Kim chiqadi?",
                    reply_markup=markup
                )

        await message.answer("Ishchi talab qilindi!")

        # Reset state
        await state.finish()
    else:
        await message.answer("Iltimos, ishchi sonini raqam sifatida kiriting.")

# Handler for "Men chiqaman" button
@dp.message_handler(lambda message: message.text == "Men chiqaman")
async def mark_attendance(message: types.Message):
    global attending_users, required_worker_count
    user_id = message.from_user.id

    # Check if the user is registered
    user = next((user for user in registered_users if user['user_id'] == user_id), None)
    if not user:
        await message.answer("Siz ro'yhatda yo'q!")
        return

    # Check if the user has already marked attendance
    if any(att_user['user_id'] == user_id for att_user in attending_users):
        await message.answer("Siz allaqachon ro'yhatdasiz!")
        return

    # Check if the required worker count is reached
    if len(attending_users) >= required_worker_count:
        await message.answer("Kerakli ishchilar soniga yetildi, boshqa qo'shilolmaysiz!")
        return

    # Add the user to attending_users
    attending_users.append(user)
    await message.answer("Siz ro'yhatga yozildingiz!")

    # Check if the required number of workers is reached
    if len(attending_users) == required_worker_count:
        user_names = [f"{idx + 1}. {att_user['first_name']} {att_user['last_name']}" 
                      for idx, att_user in enumerate(attending_users)]
        message_text = f"Ishchilar ro'yhati:\n" + "\n".join(user_names)
        
        # Send the attendance list to all users (excluding admin)
        for user in registered_users:
            if user['user_id'] != ADMIN_ID:
                await bot.send_message(user['user_id'], message_text)

# Handler for "Ishchilar ro'yhati" button (Admin)
@dp.message_handler(lambda message: message.text == "Ishchilar ro'yhati", user_id=ADMIN_ID)
async def show_attending_users_admin(message: types.Message):
    if attending_users:
        # Include phone numbers for admin
        user_names = [
            f"{idx + 1}. {user['first_name']} {user['last_name']} ({user['phone_number']})"
            for idx, user in enumerate(attending_users)
            
        ]
        try:
            await message.answer(f"Ishchilar ro'yhati (Admin):\n" + "\n".join(user_names))
        except BotBlocked:
            print(f"Admin {ADMIN_ID} has blocked the bot.")

    else:
        await message.answer("Hozircha hech kim ro'yhatga yozilmadi.")




# Handler for "Ishchilar ro'yhati" button (Users)
@dp.message_handler(lambda message: message.text == "Ishchilar ro'yhati")
async def show_attending_users(message: types.Message):
    user_id = message.from_user.id

    # Check if the user is registered
    if not any(user['user_id'] == user_id for user in registered_users):
        await message.answer("Siz ro'yhatda yo'q!")
        return

    if attending_users:
        user_names = [f"{user['first_name']} {user['last_name']}" for user in attending_users]
        try:
            await message.answer(f"Ishchi ro'yhati:\n" + "\n".join(user_names))
        except BotBlocked:
            print(f"User {user_id} has blocked the bot.")
    else:
        await message.answer("Hozircha hech kim ro'yhatga yozilmadi.")




# Handler for /clear command (Admin)
@dp.message_handler(commands=['clear'])
async def clear_user_lists(message: types.Message):
    if message.from_user.id == ADMIN_ID:  # Check if the user is the admin
        global attending_users, required_worker_count, current_date, registered_users
        attending_users.clear()
        required_worker_count = 0
        current_date = ""
        # Optionally, clear registered_users or reset specific fields
        await message.answer("Ro'yhatlar tozalandi!")
    else:
        await message.answer("Sizda bunday huquq yo'q!")

# Start the bot
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
