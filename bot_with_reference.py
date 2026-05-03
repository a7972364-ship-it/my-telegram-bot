import os, json, base64, re, requests, asyncio
from datetime import datetime
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ConversationHandler, CallbackQueryHandler, filters, ContextTypes

TELEGRAM_TOKEN = "8651518107:AAFtxuF2KZDM4IeuGdf1bVb1_ZV01rcI5lk"
GROQ_KEY       = "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"
VERCEL_TOKEN   = os.environ.get("VERCEL_TOKEN", "")
MY_ID          = 311728841

client = Groq(api_key=GROQ_KEY, timeout=60.0)

STYLE_FILE   = "/tmp/saved_style.txt"
SITES_FILE   = "/tmp/all_sites.json"
HISTORY_FILE = "/tmp/site_history.json"

ASK_NAME, ASK_DESC, ASK_SERVICES, ASK_CONTACTS, ASK_COLORS, ASK_EXTRAS, CONFIRM = range(7)

# ─── Шаблоны ─────────────────────────────────────────────────────────────────
TEMPLATES = {
    "barber": {
        "name": "Барбершоп",
        "photo": "https://images.unsplash.com/photo-1621605815971-fbc98d665033?w=800&q=80",
        "brief": "Название: [спросить]\nОписание: Премиальный барбершоп. Стрижки, бритьё, уход за бородой.\nУслуги: Стрижка, Бритьё, Оформление бороды, Укладка\nСтиль: тёмный с золотым акцентом, мужской премиальный стиль"
    },
    "coffee": {
        "name": "Кофейня",
        "photo": "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=800&q=80",
        "brief": "Название: [спросить]\nОписание: Уютная кофейня с авторскими напитками и десертами.\nУслуги: Эспрессо, Капучино, Авторские напитки, Десерты, Завтраки\nСтиль: тёплый тёмный, коричнево-бежевые акценты"
    },
    "studio": {
        "name": "Музыкальная студия",
        "photo": "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?w=800&q=80",
        "brief": "Название: [спросить]\nОписание: Профессиональная студия звукозаписи.\nУслуги: Запись вокала, Сведение, Мастеринг, Аранжировка\nСтиль: тёмный с фиолетовым градиентом"
    },
    "fitness": {
        "name": "Фитнес / Тренер",
        "photo": "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=800&q=80",
        "brief": "Название: [спросить]\nОписание: Персональные тренировки и программы питания.\nУслуги: Персональные тренировки, Онлайн-программы, Консультации по питанию\nСтиль: тёмный с оранжево-красным акцентом, энергичный"
    },
    "portfolio": {
        "name": "Портфолио / Фрилансер",
        "photo": "https://images.unsplash.com/photo-1467232004584-a241de8bcf5d?w=800&q=80",
        "brief": "Название: [спросить]\nОписание: Портфолио дизайнера / разработчика / фотографа.\nУслуги: Работы, Обо мне, Услуги, Контакты\nСтиль: минималистичный тёмный с ярким акцентом"
    },
    "restaurant": {
        "name": "Ресторан",
        "photo": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&q=80",
        "brief": "Название: [спросить]\nОписание: Изысканный ресторан с авторской кухней.\nУслуги: Меню, Бронирование, О нас, Галерея\nСтиль: элегантный тёмный с золотым"
    },
    "beauty": {
        "name": "Салон красоты",
        "photo": "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=800&q=80",
        "brief": "Название: [спросить]\nОписание: Салон красоты полного цикла.\nУслуги: Стрижки, Окрашивание, Маникюр, Макияж, Брови\nСтиль: тёмный с розово-золотым акцентом"
    },
    "doctor": {
        "name": "Врач / Клиника",
        "photo": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=800&q=80",
        "brief": "Название: [спросить]\nОписание: Частная медицинская практика.\nУслуги: Консультации, Диагностика, Лечение, Запись онлайн\nСтиль: чистый тёмно-синий, доверительный профессиональный"
    },
}

BASE_PROMPT = """Ты веб-дизайнер. Ответ ТОЛЬКО в JSON:
{"files":{"index.html":"код"},"summary":"1-2 предложения"}

ВЕСЬ CSS в <style>, ВЕСЬ JS в <script>. CDN:
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>

СТИЛИ: *{margin:0;padding:0;box-sizing:border-box} body{background:#0a0a0a;color:#fff;font-family:Inter,sans-serif}
АДАПТИВ: @media(max-width:768px){.grid-3,.grid-2{grid-template-columns:1fr} section{padding:60px 20px} nav .links{display:none}}

СТРУКТУРА: навбар fixed blur(20px) → hero 100vh с blob и gradient заголовком → бегущая строка → 3 карточки преимуществ → услуги → CTA → футер
BLOB: position:absolute;width:500px;height:500px;border-radius:50%;filter:blur(100px);opacity:0.15;animation:blob 7s infinite
@keyframes blob{0%,100%{transform:translate(-50%,-50%)scale(1)}50%{transform:translate(-40%,-60%)scale(1.2)}}
КНОПКИ: href="https://t.me/USERNAME", href="tel:+7...", href="mailto:...", href="#section"
КАРТИНКИ: https://images.unsplash.com/photo-[релевантный ID]?w=1200&q=80
FADE-IN: IntersectionObserver на секции"""

SEO_PROMPT = """Добавь SEO оптимизацию в HTML и верни ТОЛЬКО JSON:
{
  "files": { "index.html": "полный html с SEO" },
  "summary": "что добавил"
}

Добавь в <head>:
- <title> с названием бизнеса и ключевыми словами
- <meta name="description"> 150-160 символов
- <meta name="keywords">
- Open Graph теги (og:title, og:description, og:image, og:url)
- <meta name="robots" content="index, follow">
- <link rel="canonical">
- Schema.org JSON-LD для LocalBusiness
Верни ПОЛНЫЙ файл."""

EDIT_PROMPT = """Внеси изменения в HTML и верни ТОЛЬКО JSON:
{
  "files": { "index.html": "полный обновлённый html" },
  "summary": "что изменил"
}
Сохраняй весь дизайн, меняй только запрошенное. Верни ПОЛНЫЙ файл."""

ADDBLOCK_PROMPT = """Добавь новый раздел в HTML и верни ТОЛЬКО JSON:
{
  "files": { "index.html": "полный html с новым разделом" },
  "summary": "что добавил"
}
Стиль раздела должен совпадать с остальным сайтом. Добавь ссылку в навбар. Верни ПОЛНЫЙ файл."""

STYLE_ADDON = "\n\nСОХРАНЁННЫЙ СТИЛЬ (применяй строго):\n{style_description}"


# ─── Утилиты ─────────────────────────────────────────────────────────────────

def load_style() -> str | None:
    try: return open(STYLE_FILE).read().strip() if os.path.exists(STYLE_FILE) else None
    except: return None

def save_style(d): open(STYLE_FILE, "w").write(d)

def load_sites() -> list:
    try: return json.load(open(SITES_FILE)) if os.path.exists(SITES_FILE) else []
    except: return []

def save_site_to_list(name: str, url: str):
    sites = load_sites()
    sites.append({"name": name, "url": url, "date": datetime.now().strftime("%d.%m.%Y %H:%M")})
    json.dump(sites[-20:], open(SITES_FILE, "w"), ensure_ascii=False)

def load_history() -> list:
    try: return json.load(open(HISTORY_FILE)) if os.path.exists(HISTORY_FILE) else []
    except: return []

def push_history(files: dict, url: str, name: str = ""):
    history = load_history()
    history.append({"files": files, "url": url, "name": name, "date": datetime.now().strftime("%d.%m.%Y %H:%M")})
    json.dump(history[-5:], open(HISTORY_FILE, "w"), ensure_ascii=False)

def pop_history() -> dict | None:
    history = load_history()
    if len(history) < 2: return None
    history.pop()
    json.dump(history, open(HISTORY_FILE, "w"), ensure_ascii=False)
    return history[-1] if history else None

def current_site() -> dict | None:
    history = load_history()
    return history[-1] if history else None

def build_prompt() -> str:
    style = load_style()
    return BASE_PROMPT + (STYLE_ADDON.format(style_description=style) if style else "")

def parse_response(raw: str) -> tuple[dict, str]:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    return data.get("files", {}), data.get("summary", "Готово!")

def deploy(files: dict) -> str:
    vfiles = [{"file": n, "data": base64.b64encode(c.encode()).decode(), "encoding": "base64"} for n,c in files.items()]
    r = requests.post(
        "https://api.vercel.com/v13/deployments",
        headers={"Authorization": f"Bearer {VERCEL_TOKEN}", "Content-Type": "application/json"},
        data=json.dumps({"name": "my-telegram-sites", "files": vfiles, "projectSettings": {"framework": None}}),
        timeout=60
    )
    if r.status_code not in (200, 201): raise RuntimeError(f"Vercel {r.status_code}: {r.text[:200]}")
    url = r.json().get("url", "")
    return ("https://" + url) if not url.startswith("http") else url

def get_qr_url(site_url: str) -> str:
    return f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={site_url}&bgcolor=0a0a0a&color=ffffff&margin=20"

def analyze_style(b64: str) -> str:
    r = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct", max_tokens=1000,
        messages=[
            {"role": "system", "content": "Опиши визуальный стиль сайта: цвета (hex), шрифты, отступы, кнопки, карточки, анимации."},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": "Опиши стиль детально."}
            ]}
        ]
    )
    return r.choices[0].message.content.strip()

def build_brief(data: dict) -> str:
    template_context = ""
    if data.get("template_brief"):
        template_context = f"\nШАБЛОН: {data['template_brief']}\n"
    return f"""{template_context}
Создай лендинг:
Название: {data.get('name', '')}
Описание: {data.get('desc', '')}
Услуги: {data.get('services', '')}
Контакты: {data.get('contacts', '')}
Цвета: {data.get('colors', 'тёмная премиальная')}
Дополнительно: {data.get('extras', 'нет')}

Используй эти данные везде. Не оставляй заглушки типа [название]."""


# ─── Главное меню (inline кнопки) ────────────────────────────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Создать сайт", callback_data="menu_new"),
         InlineKeyboardButton("🎨 Шаблоны", callback_data="menu_templates")],
        [InlineKeyboardButton("✏️ Редактировать", callback_data="menu_edit"),
         InlineKeyboardButton("➕ Добавить раздел", callback_data="menu_addblock")],
        [InlineKeyboardButton("🔍 SEO", callback_data="menu_seo"),
         InlineKeyboardButton("📱 QR-код", callback_data="menu_qr")],
        [InlineKeyboardButton("↩️ Отменить изменение", callback_data="menu_undo"),
         InlineKeyboardButton("📋 Мои сайты", callback_data="menu_list")],
        [InlineKeyboardButton("🎭 Стиль по скриншоту", callback_data="menu_setstyle"),
         InlineKeyboardButton("🗑 Сбросить стиль", callback_data="menu_clearstyle")],
    ])

def templates_keyboard():
    buttons = []
    row = []
    for key, t in TEMPLATES.items():
        row.append(InlineKeyboardButton(t["name"], callback_data=f"tpl_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="menu_back")])
    return InlineKeyboardMarkup(buttons)


# ─── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    style = load_style()
    site  = current_site()
    text = (
        "👋 Привет! Создаю премиальные сайты.\n\n"
        + ("✅ Стиль сохранён\n" if style else "⚪ Стиль не задан\n")
        + (f"🌐 Последний: {site['url']}\n" if site else "⚪ Сайтов ещё нет\n")
        + "\nВыбери действие:"
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_back":
        await query.edit_message_text("Выбери действие:", reply_markup=main_menu_keyboard())

    elif data == "menu_new":
        await query.edit_message_text("🌐 Создаём сайт!\n\n1️⃣ Как называется твой бизнес?")
        context.user_data["brief"] = {}
        context.user_data["conv_state"] = ASK_NAME

    elif data == "menu_templates":
        await query.edit_message_text("🎨 Выбери шаблон:", reply_markup=templates_keyboard())

    elif data.startswith("tpl_"):
        key = data[4:]
        tpl = TEMPLATES.get(key)
        if not tpl: return
        await query.message.reply_photo(
            photo=tpl["photo"],
            caption=f"*{tpl['name']}*\n\nКак называется твой бизнес?",
            parse_mode="Markdown"
        )
        context.user_data["brief"] = {"template_brief": tpl["brief"]}
        context.user_data["conv_state"] = ASK_NAME

    elif data == "menu_edit":
        site = current_site()
        if not site:
            await query.edit_message_text("⚪ Нет сохранённого сайта. Сначала создай через меню.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text("✏️ Напиши что изменить (одним сообщением):\n\nПример: измени цвет кнопок на золотой")
        context.user_data["action"] = "edit"

    elif data == "menu_addblock":
        site = current_site()
        if not site:
            await query.edit_message_text("⚪ Нет сайта. Сначала создай через меню.", reply_markup=main_menu_keyboard())
            return
        await query.edit_message_text("➕ Напиши какой раздел добавить:\n\nПример: секция с отзывами\nПример: блок с ценами")
        context.user_data["action"] = "addblock"

    elif data == "menu_seo":
        site = current_site()
        if not site:
            await query.edit_message_text("⚪ Нет сайта.", reply_markup=main_menu_keyboard())
            return
        msg = await query.edit_message_text("🔍 Добавляю SEO оптимизацию...")
        try:
            html = site["files"].get("index.html", "")
            r = client.chat.completions.create(
                model="llama-3.3-70b-versatile", max_tokens=8000,
                messages=[{"role": "system", "content": SEO_PROMPT}, {"role": "user", "content": f"HTML:\n{html}"}]
            )
            files, summary = parse_response(r.choices[0].message.content)
            url = deploy(files)
            push_history(files, url, site.get("name", ""))
            save_site_to_list(site.get("name", "сайт"), url)
            await msg.edit_text(f"✅ SEO добавлен!\n\n🌐 {url}\n\n📝 {summary}", reply_markup=main_menu_keyboard())
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu_keyboard())

    elif data == "menu_qr":
        site = current_site()
        if not site:
            await query.edit_message_text("⚪ Нет сайта.", reply_markup=main_menu_keyboard())
            return
        qr_url = get_qr_url(site["url"])
        await query.message.reply_photo(
            photo=qr_url,
            caption=f"📱 QR-код для:\n{site['url']}\n\nРаспечатай и размести где нужно!"
        )
        await query.edit_message_text("Выбери действие:", reply_markup=main_menu_keyboard())

    elif data == "menu_undo":
        prev = pop_history()
        if not prev:
            await query.edit_message_text("⚪ Нет предыдущей версии.", reply_markup=main_menu_keyboard())
            return
        msg = await query.edit_message_text("↩️ Откатываю к предыдущей версии...")
        try:
            url = deploy(prev["files"])
            await msg.edit_text(f"✅ Откатил!\n\n🌐 {url}", reply_markup=main_menu_keyboard())
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu_keyboard())

    elif data == "menu_list":
        sites = load_sites()
        if not sites:
            await query.edit_message_text("⚪ Сайтов ещё нет.", reply_markup=main_menu_keyboard())
            return
        text = "📋 Все твои сайты:\n\n"
        for i, s in enumerate(reversed(sites[-10:]), 1):
            text += f"{i}. {s.get('name', 'Сайт')} — {s['date']}\n🌐 {s['url']}\n\n"
        await query.edit_message_text(text, reply_markup=main_menu_keyboard())

    elif data == "menu_setstyle":
        await query.edit_message_text("📸 Отправь скриншот сайта — запомню стиль навсегда.")
        context.user_data["waiting_for_style"] = True

    elif data == "menu_clearstyle":
        if os.path.exists(STYLE_FILE): os.remove(STYLE_FILE)
        await query.edit_message_text("🗑 Стиль сброшен.", reply_markup=main_menu_keyboard())


# ─── Текстовые сообщения (диалог и действия) ─────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    text  = update.message.text.strip()
    state = context.user_data.get("conv_state")
    action= context.user_data.get("action")

    # Диалог создания сайта
    if state == ASK_NAME:
        context.user_data["brief"]["name"] = text
        context.user_data["conv_state"] = ASK_DESC
        await update.message.reply_text("2️⃣ Опиши чем занимаешься (1-2 предложения):")
        return

    if state == ASK_DESC:
        context.user_data["brief"]["desc"] = text
        context.user_data["conv_state"] = ASK_SERVICES
        await update.message.reply_text("3️⃣ Перечисли услуги через запятую:")
        return

    if state == ASK_SERVICES:
        context.user_data["brief"]["services"] = text
        context.user_data["conv_state"] = ASK_CONTACTS
        await update.message.reply_text("4️⃣ Контакты — Telegram, телефон, email (что есть):")
        return

    if state == ASK_CONTACTS:
        context.user_data["brief"]["contacts"] = text
        context.user_data["conv_state"] = ASK_COLORS
        await update.message.reply_text(
            "5️⃣ Стиль сайта:",
            reply_markup=ReplyKeyboardMarkup([
                ["🖤 Тёмный с фиолетовым"],
                ["🖤 Тёмный с золотым"],
                ["🖤 Тёмный с синим"],
                ["🤍 Светлый минимализм"],
                ["✍️ Напишу сам"]
            ], one_time_keyboard=True, resize_keyboard=True)
        )
        return

    if state == ASK_COLORS:
        context.user_data["brief"]["colors"] = text
        context.user_data["conv_state"] = ASK_EXTRAS
        await update.message.reply_text(
            "6️⃣ Что добавить? (или «нет»)\nПример: цены, портфолио, отзывы, FAQ",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    if state == ASK_EXTRAS:
        context.user_data["brief"]["extras"] = text
        context.user_data["conv_state"] = CONFIRM
        b = context.user_data["brief"]
        await update.message.reply_text(
            f"✅ Проверь данные:\n\n"
            f"🏷 {b.get('name')}\n"
            f"📝 {b.get('desc')}\n"
            f"⚡ {b.get('services')}\n"
            f"📞 {b.get('contacts')}\n"
            f"🎨 {b.get('colors')}\n"
            f"➕ {b.get('extras')}\n\nВсё верно?",
            reply_markup=ReplyKeyboardMarkup([["✅ Да, создавай!", "❌ Начать заново"]], one_time_keyboard=True, resize_keyboard=True)
        )
        return

    if state == CONFIRM:
        if "заново" in text.lower():
            context.user_data["brief"] = {}
            context.user_data["conv_state"] = ASK_NAME
            await update.message.reply_text("Хорошо! Как называется бизнес?", reply_markup=ReplyKeyboardRemove())
            return
        context.user_data["conv_state"] = None
        status = await update.message.reply_text("🤖 Создаю сайт...", reply_markup=ReplyKeyboardRemove())
        try:
            brief_text = build_brief(context.user_data["brief"])
            await status.edit_text("🤖 Groq пишет код... (~30 сек)")

            def call_groq():
                return client.chat.completions.create(
                    model="llama-3.3-70b-versatile", max_tokens=6000,
                    messages=[{"role": "system", "content": build_prompt()}, {"role": "user", "content": brief_text}]
                )

            try:
                r = await asyncio.wait_for(asyncio.to_thread(call_groq), timeout=80)
            except asyncio.TimeoutError:
                await status.edit_text("❌ Groq не ответил за 80 сек. Попробуй ещё раз.", reply_markup=main_menu_keyboard())
                return

            raw = r.choices[0].message.content
            await status.edit_text("🔧 Обрабатываю код...")

            try:
                files, summary = parse_response(raw)
            except Exception as parse_err:
                await status.edit_text(f"❌ Ошибка парсинга: {str(parse_err)[:150]}\n\nПопробуй ещё раз.", reply_markup=main_menu_keyboard())
                return

            if not files:
                await status.edit_text("❌ Groq не вернул файлы. Попробуй ещё раз.", reply_markup=main_menu_keyboard())
                return

            await status.edit_text("🚀 Деплою на Vercel...")
            url = deploy(files)
            name = context.user_data["brief"].get("name", "Сайт")
            push_history(files, url, name)
            save_site_to_list(name, url)
            qr_url = get_qr_url(url)
            await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}", reply_markup=main_menu_keyboard())
            await update.message.reply_photo(photo=qr_url, caption="📱 QR-код твоего сайта")
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {str(e)[:300]}", reply_markup=main_menu_keyboard())
        return

    # Действия edit/addblock
    if action == "edit":
        context.user_data["action"] = None
        site = current_site()
        if not site:
            await update.message.reply_text("⚪ Нет сайта.", reply_markup=main_menu_keyboard())
            return
        status = await update.message.reply_text("✏️ Вношу изменения...")
        try:
            html = site["files"].get("index.html", "")
            r = client.chat.completions.create(
                model="llama-3.3-70b-versatile", max_tokens=8000,
                messages=[{"role": "system", "content": EDIT_PROMPT}, {"role": "user", "content": f"HTML:\n{html}\n\nЧТО ИЗМЕНИТЬ: {text}"}]
            )
            files, summary = parse_response(r.choices[0].message.content)
            url = deploy(files)
            push_history(files, url, site.get("name", ""))
            save_site_to_list(site.get("name", ""), url)
            await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}", reply_markup=main_menu_keyboard())
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu_keyboard())
        return

    if action == "addblock":
        context.user_data["action"] = None
        site = current_site()
        if not site:
            await update.message.reply_text("⚪ Нет сайта.", reply_markup=main_menu_keyboard())
            return
        status = await update.message.reply_text("➕ Добавляю раздел...")
        try:
            html = site["files"].get("index.html", "")
            r = client.chat.completions.create(
                model="llama-3.3-70b-versatile", max_tokens=8000,
                messages=[{"role": "system", "content": ADDBLOCK_PROMPT}, {"role": "user", "content": f"HTML:\n{html}\n\nДОБАВИТЬ: {text}"}]
            )
            files, summary = parse_response(r.choices[0].message.content)
            url = deploy(files)
            push_history(files, url, site.get("name", ""))
            save_site_to_list(site.get("name", ""), url)
            await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}", reply_markup=main_menu_keyboard())
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu_keyboard())
        return

    # Если ничего не ожидается — показываем меню
    await update.message.reply_text("Выбери действие:", reply_markup=main_menu_keyboard())


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    photo = update.message.photo[-1]
    f     = await context.bot.get_file(photo.file_id)
    data  = await f.download_as_bytearray()
    b64   = base64.b64encode(bytes(data)).decode()

    if context.user_data.get("waiting_for_style"):
        context.user_data["waiting_for_style"] = False
        status = await update.message.reply_text("🔍 Анализирую стиль...")
        try:
            save_style(analyze_style(b64))
            await status.edit_text("✅ Стиль сохранён! Все сайты теперь в этом стиле.", reply_markup=main_menu_keyboard())
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {e}")
        return

    await update.message.reply_text("Чтобы сохранить стиль — нажми «Стиль по скриншоту» в меню /start", reply_markup=main_menu_keyboard())


async def post_init(app):
    await app.bot.set_my_commands([
        ("start", "Главное меню"),
    ])


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("✅ Бот запущен!")
    app.run_polling()
