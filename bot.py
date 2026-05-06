import json
import logging
import os
import secrets
from datetime import datetime
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

# ──────────────────────────────────────────────
# Настройки
# ──────────────────────────────────────────────
BOT_TOKEN         = os.environ["BOT_TOKEN"]
GOOGLE_CREDS_FILE = os.getenv("GOOGLE_CREDS_FILE", "credentials.json")
SPREADSHEET_NAME  = os.getenv("SPREADSHEET_NAME", "Школьные анкеты")
ADMIN_IDS         = [int(i) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
TOKENS_FILE       = "tokens.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Google Sheets
# ──────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ──────────────────────────────────────────────
# Токены приглашений
# ──────────────────────────────────────────────

def load_tokens() -> dict:
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_tokens(tokens: dict):
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)


def get_sheet(sheet_name: str):
    creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open(SPREADSHEET_NAME)
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=30)


def ensure_header(sheet, headers: list):
    existing = sheet.row_values(1)
    if not existing:
        sheet.append_row(headers, value_input_option="USER_ENTERED")


def save_to_sheets(role: str, user_data: dict, user_id: int, username: str):
    sheet_name = "Родители" if role == "parent" else "Ученики"
    sheet = get_sheet(sheet_name)

    questions = get_questions(role)
    answers = user_data.get("answers", {})

    # Шапка
    headers = [
        "Дата и время", "Telegram ID", "Username",
        "Имя", "Фамилия", "Класс",
    ] + [q["header"] for q in questions]
    ensure_header(sheet, headers)

    # Строка данных
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        str(user_id),
        f"@{username}" if username else "—",
        user_data.get("first_name", ""),
        user_data.get("last_name", ""),
        user_data.get("class_name", ""),
    ] + [answers.get(q["id"], "—") for q in questions]

    sheet.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"Saved to Sheets [{sheet_name}]: user={user_id}")


# ──────────────────────────────────────────────
# Анкета для РОДИТЕЛЕЙ
# ──────────────────────────────────────────────
QUESTIONS_PARENTS = [
    {
        "id": "p1", "header": "Атмосфера и безопасность",
        "section": "📋 Общие вопросы",
        "text": "Как Вы оцениваете общую атмосферу и уровень безопасности в школе?",
        "type": "choice",
        "options": ["⭐⭐⭐⭐⭐ Очень хороший", "⭐⭐⭐⭐ Хороший", "⭐⭐⭐ Средний", "⭐⭐ Плохой", "⭐ Очень плохой"],
    },
    {
        "id": "p2", "header": "Условия обучения",
        "section": None,
        "text": "Удовлетворены ли Вы условиями обучения?\n(классы, оборудование, учебные материалы)",
        "type": "choice",
        "options": ["✅ Да, полностью", "🟢 В основном да", "🟡 Не очень", "🔴 Нет, есть проблемы"],
    },
    {
        "id": "p3", "header": "Коммуникация со школой",
        "section": None,
        "text": "Насколько Вы удовлетворены коммуникацией со школой?\n(новости, анкеты, родительские собрания)",
        "type": "choice",
        "options": ["😊 Очень доволен(а)", "🙂 Доволен(а)", "😐 Нейтрально", "🙁 Недоволен(а)", "😞 Очень недоволен(а)"],
    },
    {
        "id": "p4", "header": "Профессионализм учителей",
        "section": "👩‍🏫 Учителя и педагогический процесс",
        "text": "Как Вы оцениваете профессионализм и компетентность учителей?",
        "type": "choice",
        "options": ["⭐⭐⭐⭐⭐ Отлично", "⭐⭐⭐⭐ Хорошо", "⭐⭐⭐ Удовлетворительно", "⭐⭐ Плохо", "⭐ Очень плохо"],
    },
    {
        "id": "p5", "header": "Доступность объяснений",
        "section": None,
        "text": "Насколько доступно и понятно учителя объясняют учебный материал?",
        "type": "choice",
        "options": ["✅ Всегда понятно", "🟢 Часто понятно", "🟡 Иногда понятно", "🟠 Редко понятно", "🔴 Никогда"],
    },
    {
        "id": "p6", "header": "Отношение учителей",
        "section": None,
        "text": "Как Вы оцениваете отношение учителей к ученикам и родителям?",
        "type": "choice",
        "options": ["😊 Очень хорошее", "🙂 Хорошее", "😐 Среднее", "🙁 Плохое", "😞 Очень плохое"],
    },
    {
        "id": "p7", "header": "Разнообразие уроков",
        "section": None,
        "text": "Насколько учителя проводят интересные и разнообразные уроки?",
        "type": "choice",
        "options": ["✅ Всегда", "🟢 Часто", "🟡 Иногда", "🟠 Редко", "🔴 Никогда"],
    },
    {
        "id": "p8", "header": "Пожелания по учителям",
        "section": None,
        "text": "📝 Пожелания или предложения по работе учителей?\n\n_(Напишите текстом или нажмите «Пропустить»)_",
        "type": "text",
    },
    {
        "id": "p9", "header": "Школьные мероприятия",
        "section": "🎭 Внеклассная работа",
        "text": "Участвует ли школа в проведении мероприятий, интересных для Ваших детей?",
        "type": "choice",
        "options": ["🎉 Да, очень активно", "🟢 В основном да", "🟡 Иногда", "🔴 Нет"],
    },
    {
        "id": "p10", "header": "Учёт мнения родителей",
        "section": None,
        "text": "Насколько школа и учителя учитывают мнение родителей?",
        "type": "choice",
        "options": ["⭐⭐⭐⭐⭐ Очень хорошо", "⭐⭐⭐⭐ Хорошо", "⭐⭐⭐ Средне", "⭐⭐ Плохо"],
    },
    {
        "id": "p11", "header": "Успехи школы",
        "section": "🏆 Итоговые вопросы",
        "text": "📝 В чём школа достигает успехов?\n\n_(Напишите текстом или нажмите «Пропустить»)_",
        "type": "text",
    },
    {
        "id": "p12", "header": "Что улучшить",
        "section": None,
        "text": "📝 Какие аспекты работы школы требуют улучшения?\n\n_(Напишите текстом или нажмите «Пропустить»)_",
        "type": "text",
    },
    {
        "id": "p13", "header": "Общие рекомендации",
        "section": None,
        "text": "📝 Общие рекомендации для повышения качества образования.\n\n_(Напишите текстом или нажмите «Пропустить»)_",
        "type": "text",
    },
]

# ──────────────────────────────────────────────
# Анкета для УЧЕНИКОВ
# ──────────────────────────────────────────────
QUESTIONS_STUDENTS = [
    {
        "id": "s1", "header": "Нравится ли школа",
        "section": "🏫 Об атмосфере в школе",
        "text": "Тебе нравится ходить в школу?",
        "type": "choice",
        "options": ["😍 Очень нравится", "🙂 В целом да", "😐 Так себе", "😕 Не очень", "😞 Совсем не нравится"],
    },
    {
        "id": "s2", "header": "Чувство безопасности",
        "section": None,
        "text": "Чувствуешь ли ты себя в безопасности в школе?",
        "type": "choice",
        "options": ["✅ Да, всегда", "🟢 В основном да", "🟡 Иногда нет", "🔴 Нет, не чувствую"],
    },
    {
        "id": "s3", "header": "Отношения с одноклассниками",
        "section": None,
        "text": "Как ты относишься к одноклassникам?",
        "type": "choice",
        "options": ["😊 Отлично, дружим", "🙂 Хорошо", "😐 Нейтрально", "🙁 Есть конфликты", "😞 Очень плохо"],
    },
    {
        "id": "s4", "header": "Интересность уроков",
        "section": "📚 Об учёбе и учителях",
        "text": "Насколько интересно учителя проводят уроки?",
        "type": "choice",
        "options": ["🔥 Всегда интересно", "🟢 Часто интересно", "🟡 Иногда", "🟠 Редко", "😴 Очень скучно"],
    },
    {
        "id": "s5", "header": "Понятность объяснений",
        "section": None,
        "text": "Понятно ли учителя объясняют новый материал?",
        "type": "choice",
        "options": ["✅ Всегда понятно", "🟢 Обычно понятно", "🟡 Иногда непонятно", "🔴 Часто непонятно"],
    },
    {
        "id": "s6", "header": "Отношение учителей",
        "section": None,
        "text": "Как учителя относятся к тебе и другим ученикам?",
        "type": "choice",
        "options": ["😊 Очень хорошо", "🙂 Хорошо", "😐 По-разному", "🙁 Не очень хорошо", "😞 Плохо"],
    },
    {
        "id": "s7", "header": "Справедливость оценок",
        "section": None,
        "text": "Справедливо ли учителя оценивают твои знания?",
        "type": "choice",
        "options": ["✅ Всегда справедливо", "🟢 Обычно да", "🟡 Иногда несправедливо", "🔴 Часто несправедливо"],
    },
    {
        "id": "s8", "header": "Школьные мероприятия",
        "section": "🎭 Жизнь в школе",
        "text": "Нравятся ли тебе школьные мероприятия и праздники?",
        "type": "choice",
        "options": ["🎉 Да, очень!", "🟢 В основном да", "🟡 Иногда", "🔴 Не очень", "😞 Совсем не нравятся"],
    },
    {
        "id": "s9", "header": "Что нравится в школе",
        "section": "💬 Твоё мнение",
        "text": "📝 Что тебе больше всего нравится в твоей школе?\n\n_(Напиши текстом или нажми «Пропустить»)_",
        "type": "text",
    },
    {
        "id": "s10", "header": "Что улучшить",
        "section": None,
        "text": "📝 Что бы ты хотел(а) изменить или улучшить в школе?\n\n_(Напиши текстом или нажми «Пропустить»)_",
        "type": "text",
    },
]

# ──────────────────────────────────────────────
# Шаги сбора личных данных
# ──────────────────────────────────────────────
PERSONAL_STEPS = ["ask_first_name", "ask_last_name", "ask_class"]

def get_questions(role: str) -> list:
    return QUESTIONS_PARENTS if role == "parent" else QUESTIONS_STUDENTS


def get_user_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "answers" not in context.user_data:
        context.user_data.update({
            "answers": {},
            "step": 0,
            "personal_step": "ask_first_name",  # текущий шаг личных данных
            "role": None,
            "first_name": "",
            "last_name": "",
            "class_name": "",
            "started_at": datetime.now().isoformat(),
        })
    return context.user_data


def clean_option(text: str) -> str:
    parts = text.split(" ", 1)
    return parts[1] if len(parts) > 1 else text


def progress_bar(step: int, total: int) -> str:
    filled = round(step / total * 10)
    return f"[{'█' * filled}{'░' * (10 - filled)}] {step}/{total}"


def build_choice_keyboard(options: list, question_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(opt, callback_data=f"ans:{question_id}:{i}")] for i, opt in enumerate(options)]
    )


def build_skip_keyboard(question_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Пропустить", callback_data=f"ans:{question_id}:skip")]])


async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, step: int, edit: bool = False):
    role = context.user_data.get("role", "parent")
    questions = get_questions(role)
    q = questions[step]
    total = len(questions)

    section_header = f"*{q['section']}*\n\n" if q.get("section") else ""
    progress = progress_bar(step, total)
    text = f"{section_header}_{progress}_\n\n{q['text']}"

    keyboard = (
        build_choice_keyboard(q["options"], q["id"])
        if q["type"] == "choice"
        else build_skip_keyboard(q["id"])
    )

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        target = update.message or (update.callback_query.message if update.callback_query else None)
        await target.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


# ──────────────────────────────────────────────
# Обработчики
# ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    get_user_data(context)

    payload = context.args[0] if context.args else None

    if payload:
        tokens = load_tokens()
        if payload in tokens:
            token_data = tokens[payload]
            role = token_data["role"]

            context.user_data["role"]          = role
            context.user_data["personal_step"] = "ask_first_name"

            role_label  = "родителей" if role == "parent" else "учеников"
            name_prompt = "ваше *имя*" if role == "parent" else "своё *имя*"

            await update.message.reply_text(
                f"👋 *Добро пожаловать в школьный опрос!*\n\n"
                f"Вы проходите анкету как: *{role_label}*.\n\n"
                f"✏️ Напишите {name_prompt}:",
                parse_mode="Markdown",
            )
            return

    # Нет токена или токен неверный
    await update.message.reply_text(
        "⚠️ *Для участия в опросе используйте ссылку от вашего учителя.*\n\n"
        "Если у вас нет ссылки — обратитесь к классному руководителю.",
        parse_mode="Markdown",
    )


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = get_user_data(context)
    role = user_data.get("role")
    if not role:
        return

    personal_step = user_data.get("personal_step")
    text = update.message.text.strip()

    # ── Шаг 1: имя ──
    if personal_step == "ask_first_name":
        user_data["first_name"] = text
        user_data["personal_step"] = "ask_last_name"
        prompt = "✏️ Теперь напишите вашу *фамилию*:" if role == "parent" else "✏️ Теперь напиши свою *фамилию*:"
        await update.message.reply_text(prompt, parse_mode="Markdown")
        return

    # ── Шаг 2: фамилия ──
    if personal_step == "ask_last_name":
        user_data["last_name"] = text
        user_data["personal_step"] = "ask_class"
        prompt = "✏️ Укажите класс вашего ребёнка\n_(например: 5А, 10Б)_:" if role == "parent" \
            else "✏️ Укажи свой класс\n_(например: 5А, 10Б)_:"
        await update.message.reply_text(prompt, parse_mode="Markdown")
        return

    # ── Шаг 3: класс → начать анкету ──
    if personal_step == "ask_class":
        user_data["class_name"] = text.upper()
        user_data["personal_step"] = "survey"
        user_data["step"] = 0
        user_data["answers"] = {}

        questions = get_questions(role)
        total = len(questions)
        fname = user_data["first_name"]
        lname = user_data["last_name"]
        cls   = user_data["class_name"]

        if role == "parent":
            intro = (
                f"✅ *{fname} {lname}*, класс *{cls}*\n\n"
                f"📋 Анкета для родителей — *{total} вопросов*\n"
                f"Примерное время: 3–5 минут.\n\n"
                f"Нажмите «Начать», когда будете готовы."
            )
        else:
            intro = (
                f"✅ *{fname} {lname}*, класс *{cls}*\n\n"
                f"📋 Анкета для учеников — *{total} вопросов*\n"
                f"Примерное время: 2–3 минуты.\n\n"
                f"Нажми «Начать», когда будешь готов(а)."
            )

        await update.message.reply_text(
            intro,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Начать", callback_data="survey:begin")]]),
        )
        return

    # ── Текстовый ответ на вопрос анкеты ──
    if personal_step == "survey":
        questions = get_questions(role)
        step = user_data.get("step", 0)

        if step >= len(questions) or questions[step]["type"] != "text":
            return

        user_data["answers"][questions[step]["id"]] = text
        next_step = step + 1
        user_data["step"] = next_step

        if next_step >= len(questions):
            await finish(update, context, edit=False)
        else:
            await send_question(update, context, step=next_step, edit=False)


async def handle_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await send_question(update, context, step=0, edit=True)


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, question_id, value = query.data.split(":", 2)

    user_data = get_user_data(context)
    role = user_data.get("role", "parent")
    questions = get_questions(role)
    step = user_data["step"]

    if questions[step]["id"] != question_id:
        return

    answer_text = "—" if value == "skip" else clean_option(questions[step]["options"][int(value)])
    user_data["answers"][question_id] = answer_text

    next_step = step + 1
    user_data["step"] = next_step

    if next_step >= len(questions):
        await finish(update, context, edit=True)
    else:
        await send_question(update, context, step=next_step, edit=True)


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool):
    user = update.effective_user
    role = context.user_data.get("role", "parent")

    # Сохраняем в Google Sheets
    try:
        save_to_sheets(role, context.user_data, user.id, user.username)
        sheets_status = "✅ Ответы сохранены в таблицу."
    except Exception as e:
        logger.error(f"Google Sheets error: {e}")
        sheets_status = "⚠️ Не удалось сохранить в таблицу, обратитесь к администратору."

    role_label = "родителя" if role == "parent" else "ученика"
    text = (
        f"✅ *Анкета заполнена!*\n\n"
        f"Спасибо за участие в опросе {role_label}! 🙏\n"
        f"{sheets_status}\n\n"
        f"_Чтобы заполнить снова — введите /start_"
    )

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

    logger.info(f"Survey done: user={user.id} role={role}")


# ──────────────────────────────────────────────
# Команды администратора
# ──────────────────────────────────────────────

async def cmd_genlinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ADMIN_IDS and user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    # Необязательная метка (например, ФИО учителя) — только для удобства в /listlinks
    label = " ".join(context.args) if context.args else "без метки"

    tokens = load_tokens()

    parent_token  = secrets.token_urlsafe(8)
    student_token = secrets.token_urlsafe(8)

    tokens[parent_token]  = {"role": "parent",  "label": label}
    tokens[student_token] = {"role": "student",  "label": label}
    save_tokens(tokens)

    bot_username  = (await context.bot.get_me()).username
    parent_link   = f"https://t.me/{bot_username}?start={parent_token}"
    student_link  = f"https://t.me/{bot_username}?start={student_token}"

    await update.message.reply_text(
        f"✅ *Ссылки{' для: ' + label if label != 'без метки' else ''}*\n\n"
        f"👨‍👩‍👧 *Родители* (все классы учителя):\n`{parent_link}`\n\n"
        f"🎒 *Ученики* (все классы учителя):\n`{student_link}`\n\n"
        f"Класс пользователи укажут сами при заполнении.\n"
        f"⚠️ Каждую ссылку отправляйте только нужной группе!",
        parse_mode="Markdown",
    )


async def cmd_listlinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ADMIN_IDS and user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    tokens = load_tokens()
    if not tokens:
        await update.message.reply_text("Ссылок пока нет. Используйте /genlinks.")
        return

    bot_username = (await context.bot.get_me()).username
    # Группируем по метке
    by_label: dict[str, dict] = {}
    for token, data in tokens.items():
        lbl = data.get("label", "—")
        by_label.setdefault(lbl, {})[data["role"]] = token

    lines = ["📋 *Все выданные ссылки:*\n"]
    for lbl, roles in by_label.items():
        lines.append(f"*{lbl}*")
        for role, tok in roles.items():
            link = f"https://t.me/{bot_username}?start={tok}"
            role_label = "Родители" if role == "parent" else "Ученики"
            lines.append(f"  {role_label}: `{link}`")
        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ADMIN_IDS and user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    try:
        creds = Credentials.from_service_account_file(GOOGLE_CREDS_FILE, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SPREADSHEET_NAME)

        lines = [f"📊 *Статистика анкет*\n🔗 [{SPREADSHEET_NAME}]({spreadsheet.url})\n"]
        for sheet_name, label in [("Родители", "Родители"), ("Ученики", "Ученики")]:
            try:
                ws = spreadsheet.worksheet(sheet_name)
                count = max(0, len(ws.get_all_values()) - 1)  # минус шапка
                lines.append(f"👥 {label}: *{count}* ответов")
            except gspread.WorksheetNotFound:
                lines.append(f"👥 {label}: *0* ответов")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка подключения к Google Sheets:\n`{e}`", parse_mode="Markdown")


# ──────────────────────────────────────────────
# Запуск
# ──────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("genlinks",  cmd_genlinks))
    app.add_handler(CommandHandler("listlinks", cmd_listlinks))

    app.add_handler(CallbackQueryHandler(handle_begin,  pattern=r"^survey:begin$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^ans:"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
