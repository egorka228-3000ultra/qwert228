import html
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from supabase import Client, create_client
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
	Application,
	CallbackQueryHandler,
	CommandHandler,
	ContextTypes,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_SECRET_KEY")
)

if not BOT_TOKEN:
	raise RuntimeError("Не задан BOT_TOKEN в файле .env")
if not SUPABASE_URL or not SUPABASE_KEY:
	raise RuntimeError("Не заданы SUPABASE_URL и SUPABASE_KEY в файле .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DAYS = {
	1: "Понедельник",
	2: "Вторник",
	3: "Среда",
	4: "Четверг",
	5: "Пятница",
	6: "Суббота",
	7: "Воскресенье",
}

DAY_BUTTONS = {
	1: "Пн",
	2: "Вт",
	3: "Ср",
	4: "Чт",
	5: "Пт",
	6: "Сб",
	7: "Вс",
}


def get_groups() -> list[dict]:
	response = supabase.table("groups").select("id, name").order("name").execute()
	return response.data or []


def get_group(group_id: int) -> dict | None:
	response = (
		supabase.table("groups")
		.select("id, name")
		.eq("id", group_id)
		.limit(1)
		.execute()
	)
	return response.data[0] if response.data else None


def get_schedule(group_id: int, day_of_week: int) -> list[dict]:
	response = (
		supabase.table("schedule")
		.select("lesson_number, subject_name, time_start, time_end")
		.eq("group_id", group_id)
		.eq("day_of_week", day_of_week)
		.order("lesson_number")
		.execute()
	)
	return response.data or []


def clean_time(value: str | None) -> str:
	if not value:
		return "--:--"
	return str(value)[:5]


def groups_keyboard(groups: list[dict]) -> InlineKeyboardMarkup:
	buttons = [
		[InlineKeyboardButton(str(group["name"]), callback_data=f"group:{group['id']}")]
		for group in groups
	]
	return InlineKeyboardMarkup(buttons)


def days_keyboard() -> InlineKeyboardMarkup:
	buttons = [
		InlineKeyboardButton(label, callback_data=f"day:{day}")
		for day, label in DAY_BUTTONS.items()
	]
	return InlineKeyboardMarkup([
		buttons[:3],
		buttons[3:6],
		buttons[6:],
		[
			InlineKeyboardButton("Сегодня", callback_data="today"),
			InlineKeyboardButton("Сейчас", callback_data="now"),
			InlineKeyboardButton("Сменить группу", callback_data="change_group"),
		],
	])


def schedule_text(group: dict, day: int, lessons: list[dict]) -> str:
	title = f"<b>{html.escape(str(group['name']))}</b>\n{DAYS[day]}"
	if not lessons:
		return f"{title}\n\nНет занятий"

	rows = []
	for lesson in lessons:
		number = html.escape(str(lesson.get("lesson_number", "-")))
		subject = html.escape(str(lesson.get("subject_name", "Без названия")))
		start = clean_time(lesson.get("time_start"))
		end = clean_time(lesson.get("time_end"))
		rows.append(f"<b>{number} пара</b>  {start} - {end}\n{subject}")
	return f"{title}\n\n" + "\n\n".join(rows)


async def send_group_selection(update: Update, edit: bool = False) -> None:
	groups = get_groups()
	if not groups:
		text = "В базе данных пока нет групп"
		if edit and update.callback_query:
			await update.callback_query.edit_message_text(text)
		elif update.effective_message:
			await update.effective_message.reply_text(text)
		return

	text = "Выбери свою группу:"
	if edit and update.callback_query:
		await update.callback_query.edit_message_text(text, reply_markup=groups_keyboard(groups))
	elif update.effective_message:
		await update.effective_message.reply_text(text, reply_markup=groups_keyboard(groups))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await send_group_selection(update)


async def choose_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	group_id = int(query.data.split(":", 1)[1])
	group = get_group(group_id)
	if not group:
		await query.edit_message_text("Группа не найдена. Нажми /start и выбери группу заново.")
		return
	context.user_data["group_id"] = group_id
	today = datetime.now().isoweekday()
	await query.edit_message_text(
		f"Группа: <b>{html.escape(str(group['name']))}</b>\nВыбери день или команду:",
		parse_mode=ParseMode.HTML,
		reply_markup=days_keyboard(),
	)
	if today <= 7:
		await query.message.reply_text(
			schedule_text(group, today, get_schedule(group_id, today)),
			parse_mode=ParseMode.HTML,
		)


async def show_day(update: Update, context: ContextTypes.DEFAULT_TYPE, day: int) -> None:
	group_id = context.user_data.get("group_id")
	if not group_id:
		await send_group_selection(update, edit=True)
		return
	group = get_group(group_id)
	if not group:
		await send_group_selection(update, edit=True)
		return
	text = schedule_text(group, day, get_schedule(group_id, day))
	if update.callback_query:
		await update.callback_query.edit_message_text(
			text, parse_mode=ParseMode.HTML, reply_markup=days_keyboard()
		)
	elif update.effective_message:
		await update.effective_message.reply_text(
			text, parse_mode=ParseMode.HTML, reply_markup=days_keyboard()
		)


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await show_day(update, context, datetime.now().isoweekday())


async def now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	group_id = context.user_data.get("group_id")
	if not group_id:
		await send_group_selection(update)
		return
	group = get_group(group_id)
	day = datetime.now().isoweekday()
	current_time = datetime.now().time()
	lessons = get_schedule(group_id, day)
	active = None
	next_lesson = None
	for lesson in lessons:
		start = datetime.strptime(clean_time(lesson.get("time_start")), "%H:%M").time()
		end = datetime.strptime(clean_time(lesson.get("time_end")), "%H:%M").time()
		if start <= current_time <= end:
			active = lesson
			break
		if current_time < start and next_lesson is None:
			next_lesson = lesson

	if active:
		text = (
			f"<b>Сейчас идет {active.get('lesson_number')} пара</b>\n"
			f"{html.escape(str(active.get('subject_name', 'Без названия')))}\n"
			f"{clean_time(active.get('time_start'))} - {clean_time(active.get('time_end'))}"
		)
	elif next_lesson:
		text = (
			"<b>Сейчас перемена</b>\n"
			f"Следующая пара: {next_lesson.get('lesson_number')}\n"
			f"{html.escape(str(next_lesson.get('subject_name', 'Без названия')))}\n"
			f"Начало в {clean_time(next_lesson.get('time_start'))}"
		)
	else:
		text = "<b>На сегодня все пары закончились</b>"

	if update.callback_query:
		await update.callback_query.edit_message_text(
			text, parse_mode=ParseMode.HTML, reply_markup=days_keyboard()
		)
	else:
		await update.effective_message.reply_text(
			text, parse_mode=ParseMode.HTML, reply_markup=days_keyboard()
		)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	await query.answer()
	if query.data.startswith("group:"):
		await choose_group(update, context)
	elif query.data.startswith("day:"):
		await show_day(update, context, int(query.data.split(":", 1)[1]))
	elif query.data == "today":
		await today(update, context)
	elif query.data == "now":
		await now(update, context)
	elif query.data == "change_group":
		await send_group_selection(update, edit=True)


def main() -> None:
	application = Application.builder().token(BOT_TOKEN).build()
	application.add_handler(CommandHandler("start", start))
	application.add_handler(CommandHandler("help", start))
	application.add_handler(CommandHandler("today", today))
	application.add_handler(CommandHandler("now", now))
	application.add_handler(CallbackQueryHandler(button))
	application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
	main()
