import os, json, base64, re, requests, asyncio, time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

TELEGRAM_TOKEN = "8651518107:AAFtxuF2KZDM4IeuGdf1bVb1_ZV01rcI5lk"
GROQ_KEY       = "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"
VERCEL_TOKEN   = os.environ.get("VERCEL_TOKEN", "")
MY_ID          = 311728841

STYLE_FILE   = "/tmp/saved_style.txt"
SITES_FILE   = "/tmp/all_sites.json"
HISTORY_FILE = "/tmp/site_history.json"

TEMPLATES = {
    "barber":    {"name": "Барбершоп",          "photo": "https://images.unsplash.com/photo-1621605815971-fbc98d665033?w=800&q=80", "desc": "Премиальный барбершоп. Стрижки, бритьё, уход за бородой.", "services": "Стрижка, Бритьё, Борода, Укладка", "colors": "тёмный с золотым"},
    "coffee":    {"name": "Кофейня",             "photo": "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=800&q=80", "desc": "Уютная кофейня с авторскими напитками.", "services": "Эспрессо, Капучино, Авторские напитки, Десерты", "colors": "тёмный тёплый коричневый"},
    "studio":    {"name": "Музыкальная студия",  "photo": "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?w=800&q=80", "desc": "Профессиональная студия звукозаписи.", "services": "Запись, Сведение, Мастеринг, Аранжировка", "colors": "тёмный с фиолетовым"},
    "fitness":   {"name": "Фитнес / Тренер",     "photo": "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=800&q=80", "desc": "Персональные тренировки.", "services": "Персональные тренировки, Онлайн-программы, Питание", "colors": "тёмный с оранжевым"},
    "portfolio": {"name": "Портфолио",           "photo": "https://images.unsplash.com/photo-1467232004584-a241de8bcf5d?w=800&q=80", "desc": "Портфолио дизайнера / разработчика.", "services": "Работы, Обо мне, Услуги, Контакты", "colors": "минималистичный тёмный"},
    "restaurant":{"name": "Ресторан",            "photo": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&q=80", "desc": "Изысканный ресторан с авторской кухней.", "services": "Меню, Бронирование, Галерея", "colors": "элегантный тёмный с золотым"},
    "beauty":    {"name": "Салон красоты",       "photo": "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=800&q=80", "desc": "Салон красоты полного цикла.", "services": "Стрижки, Окрашивание, Маникюр, Макияж", "colors": "тёмный с розово-золотым"},
    "doctor":    {"name": "Врач / Клиника",      "photo": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=800&q=80", "desc": "Частная медицинская практика.", "services": "Консультации, Диагностика, Запись онлайн", "colors": "тёмно-синий профессиональный"},
}

SYSTEM_PROMPT = """Ты веб-дизайнер. Ответ ТОЛЬКО валидный JSON без markdown:
{"files":{"index.html":"код"},"summary":"1-2 предложения"}

ВЕСЬ CSS в <style>, ВЕСЬ JS в <script>. CDN разрешены.
Подключи: Inter шрифт от Google Fonts, GSAP от cdnjs.
Стили: тёмный фон #0a0a0a, белый текст, градиентные акценты.
Адаптив обязателен: @media(max-width:768px).
Структура: навбар→hero(100vh, blob, gradient заголовок)→преимущества→услуги→CTA→футер.
Кнопки рабочие: tel:, mailto:, t.me/, #якоря.
Картинки: images.unsplash.com по теме."""

EDIT_PROMPT = """Внеси изменения и верни ТОЛЬКО JSON без markdown:
{"files":{"index.html":"полный html"},"summary":"что изменил"}
Верни ПОЛНЫЙ файл."""

ADD_PROMPT = """Добавь раздел и верни ТОЛЬКО JSON без markdown:
{"files":{"index.html":"полный html с новым разделом"},"summary":"что добавил"}
Верни ПОЛНЫЙ файл."""

SEO_PROMPT = """Добавь SEO теги и верни ТОЛЬКО JSON без markdown:
{"files":{"index.html":"полный html с seo"},"summary":"что добавил"}
Добавь: title, meta description, og теги, schema.org. Верни ПОЛНЫЙ файл."""


# ─── Groq API ─────────────────────────────────────────────────────────────────

def groq_call(messages: list, model="llama-3.1-8b-instant", max_tokens=6000) -> str:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
        json={"model": model, "max_tokens": max_tokens, "messages": messages},
        timeout=55
    )
    if resp.status_code == 413:
        # Try with smaller model and truncated content
        raise requests.HTTPError(response=resp)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

def truncate_html(html: str, max_chars=12000) -> str:
    """Truncate HTML keeping structure intact."""
    if len(html) <= max_chars:
        return html
    # Keep head and first/last parts
    head_end = html.find("</head>")
    if head_end > 0:
        head = html[:head_end+7]
        body = html[head_end+7:]
        # Keep first 8000 and last 2000 chars of body
        if len(body) > 10000:
            body = body[:8000] + "\n<!-- ... truncated ... -->\n" + body[-2000:]
        return head + body
    return html[:max_chars]

def groq_call_with_html(system_prompt: str, html: str, instruction: str) -> str:
    """Call Groq for edit operations with automatic model/size fallback."""
    # Try with llama-3.3-70b-versatile first (128k context)
    truncated = truncate_html(html, 20000)
    user_content = f"HTML:\n{truncated}\n\n{instruction}"
    try:
        return groq_call([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ], model="llama-3.3-70b-versatile", max_tokens=6000)
    except requests.HTTPError as e:
        if e.response.status_code == 413:
            # Try with more truncated HTML
            truncated2 = truncate_html(html, 8000)
            user_content2 = f"HTML:\n{truncated2}\n\n{instruction}"
            return groq_call([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content2}
            ], model="llama-3.1-8b-instant", max_tokens=6000)
        raise


# ─── Утилиты ──────────────────────────────────────────────────────────────────

def load_style():
    try: return open(STYLE_FILE).read().strip() if os.path.exists(STYLE_FILE) else None
    except: return None

def save_style(d): open(STYLE_FILE, "w").write(d)

def load_sites():
    try: return json.load(open(SITES_FILE)) if os.path.exists(SITES_FILE) else []
    except: return []

def save_site(name, url):
    sites = load_sites()
    sites.append({"name": name, "url": url, "date": datetime.now().strftime("%d.%m.%Y %H:%M")})
    json.dump(sites[-20:], open(SITES_FILE, "w"), ensure_ascii=False)

def load_history():
    try: return json.load(open(HISTORY_FILE)) if os.path.exists(HISTORY_FILE) else []
    except: return []

def push_history(files, url, name=""):
    h = load_history()
    h.append({"files": files, "url": url, "name": name, "date": datetime.now().strftime("%d.%m.%Y %H:%M")})
    json.dump(h[-5:], open(HISTORY_FILE, "w"), ensure_ascii=False)

def pop_history():
    h = load_history()
    if len(h) < 2: return None
    h.pop()
    json.dump(h, open(HISTORY_FILE, "w"), ensure_ascii=False)
    return h[-1]

def current_site():
    h = load_history()
    return h[-1] if h else None

def parse_json(raw):
    raw = raw.strip()
    # Remove markdown code blocks
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    # Find the outermost JSON object
    start = raw.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", raw, 0)
    
    # Find matching closing brace
    depth = 0
    end = -1
    in_str = False
    escape = False
    for i, ch in enumerate(raw[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if not in_str:
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
    
    if end == -1:
        raise json.JSONDecodeError("No closing brace", raw, 0)
    
    json_str = raw[start:end+1]
    data = json.loads(json_str)
    return data.get("files", {}), data.get("summary", "Готово!")

def deploy(files):
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

def qr(url): return f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={url}&bgcolor=0a0a0a&color=ffffff&margin=20"

def build_system():
    style = load_style()
    if style:
        return SYSTEM_PROMPT + f"\n\nСТИЛЬ ПОЛЬЗОВАТЕЛЯ (применяй строго):\n{style}"
    return SYSTEM_PROMPT

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Новый сайт", callback_data="new"),
         InlineKeyboardButton("🎨 Шаблоны", callback_data="templates")],
        [InlineKeyboardButton("✏️ Редактировать", callback_data="edit"),
         InlineKeyboardButton("➕ Добавить раздел", callback_data="addblock")],
        [InlineKeyboardButton("🔍 SEO", callback_data="seo"),
         InlineKeyboardButton("📱 QR-код", callback_data="qr")],
        [InlineKeyboardButton("↩️ Отменить изменение", callback_data="undo"),
         InlineKeyboardButton("📋 Мои сайты", callback_data="list")],
        [InlineKeyboardButton("🎭 Сохранить стиль", callback_data="setstyle"),
         InlineKeyboardButton("🗑 Сбросить стиль", callback_data="clearstyle")],
    ])

def templates_menu():
    rows = []
    items = list(TEMPLATES.items())
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(items[i][1]["name"], callback_data=f"tpl_{items[i][0]}")]
        if i+1 < len(items):
            row.append(InlineKeyboardButton(items[i+1][1]["name"], callback_data=f"tpl_{items[i+1][0]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)

# Состояния пользователя
# user_data["state"]: None | "new_q1".."new_q6" | "new_confirm" | "edit" | "addblock" | "setstyle"
# user_data["brief"]: dict с данными для создания

QUESTIONS = [
    ("new_q1", "1️⃣ Как называется твой бизнес/проект?"),
    ("new_q2", "2️⃣ Опиши чем занимаешься (1-2 предложения):"),
    ("new_q3", "3️⃣ Перечисли услуги через запятую:"),
    ("new_q4", "4️⃣ Контакты — Telegram, телефон, email:"),
    ("new_q5", "5️⃣ Выбери стиль:"),
    ("new_q6", "6️⃣ Что добавить? (или напиши «нет»)\nПример: цены, отзывы, портфолио"),
]
Q_KEYS = ["name", "desc", "services", "contacts", "colors", "extras"]

COLORS_KB = ReplyKeyboardMarkup([
    ["🖤 Тёмный с фиолетовым", "🖤 Тёмный с золотым"],
    ["🖤 Тёмный с синим", "🤍 Светлый минимализм"],
], one_time_keyboard=True, resize_keyboard=True)


async def do_generate(status, name, brief_text, update=None):
    """Вызывает Groq и деплоит. Возвращает url или None."""
    try:
        def call():
            return groq_call([
                {"role": "system", "content": build_system()},
                {"role": "user", "content": brief_text}
            ])
        raw = await asyncio.wait_for(asyncio.to_thread(call), timeout=65)
        files, summary = parse_json(raw)
        if not files:
            await status.edit_text("❌ ИИ не вернул файлы. Попробуй ещё раз.", reply_markup=main_menu())
            return None
        await status.edit_text("🚀 Деплою на Vercel...")
        url = await asyncio.to_thread(deploy, files)
        push_history(files, url, name)
        save_site(name, url)
        await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}", reply_markup=main_menu())
        if update:
            await update.message.reply_photo(photo=qr(url), caption="📱 QR-код твоего сайта")
        return url
    except asyncio.TimeoutError:
        await status.edit_text("❌ ИИ не ответил (таймаут 65 сек). Попробуй ещё раз.", reply_markup=main_menu())
    except requests.HTTPError as e:
        await status.edit_text(f"❌ Groq HTTP ошибка: {e.response.status_code}\n{e.response.text[:150]}", reply_markup=main_menu())
    except json.JSONDecodeError as jde:
        # Show first 200 chars of raw response for debugging
        preview = raw[:200] if "raw" in dir() else "нет данных"
        await status.edit_text(f"❌ Неверный формат JSON.\nПревью ответа: {preview}", reply_markup=main_menu())
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {type(e).__name__}: {str(e)[:200]}", reply_markup=main_menu())
    return None


# ─── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    context.user_data["state"] = None
    style = load_style()
    site  = current_site()
    text  = ("👋 Привет! Создаю премиальные сайты.\n\n"
             + ("✅ Стиль сохранён\n" if style else "⚪ Стиль не задан\n")
             + (f"🌐 Последний: {site['url']}\n" if site else "⚪ Сайтов ещё нет\n")
             + "\nВыбери действие:")
    await update.message.reply_text(text, reply_markup=main_menu())

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    status = await update.message.reply_text("🔍 Тестирую Groq API...")
    try:
        t0 = time.time()
        answer = await asyncio.wait_for(
            asyncio.to_thread(groq_call, [{"role": "user", "content": "Reply with just: WORKS"}], "llama-3.1-8b-instant", 20),
            timeout=30
        )
        elapsed = round(time.time() - t0, 1)
        await status.edit_text(f"✅ Groq работает! ({elapsed}с)\nОтвет: {answer.strip()}")
    except asyncio.TimeoutError:
        await status.edit_text("❌ Groq не ответил за 30с — проблема с сетью/ключом")
    except requests.HTTPError as e:
        await status.edit_text(f"❌ HTTP {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        await status.edit_text(f"❌ {type(e).__name__}: {str(e)[:200]}")

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    q = update.callback_query
    await q.answer()
    d = q.data

    if d == "back":
        await q.edit_message_text("Выбери действие:", reply_markup=main_menu())

    elif d == "new":
        context.user_data.update({"state": "new_q1", "brief": {}})
        await q.edit_message_text(QUESTIONS[0][1])

    elif d == "templates":
        await q.edit_message_text("🎨 Выбери шаблон:", reply_markup=templates_menu())

    elif d.startswith("tpl_"):
        key = d[4:]
        tpl = TEMPLATES.get(key, {})
        context.user_data.update({
            "state": "new_q1",
            "brief": {"desc": tpl.get("desc",""), "services": tpl.get("services",""), "colors": tpl.get("colors","")},
            "tpl_name": tpl.get("name","")
        })
        await q.message.reply_photo(photo=tpl["photo"], caption=f"*{tpl['name']}*\n\n1️⃣ Как называется твой бизнес?", parse_mode="Markdown")

    elif d == "edit":
        site = current_site()
        if not site:
            await q.edit_message_text("⚪ Нет сайта. Сначала создай через меню.", reply_markup=main_menu())
            return
        context.user_data["state"] = "edit"
        await q.edit_message_text("✏️ Напиши что изменить:\n\nПример: измени цвет кнопок на золотой")

    elif d == "addblock":
        site = current_site()
        if not site:
            await q.edit_message_text("⚪ Нет сайта.", reply_markup=main_menu())
            return
        context.user_data["state"] = "addblock"
        await q.edit_message_text("➕ Напиши какой раздел добавить:\n\nПример: секция с отзывами")

    elif d == "seo":
        site = current_site()
        if not site:
            await q.edit_message_text("⚪ Нет сайта.", reply_markup=main_menu())
            return
        msg = await q.edit_message_text("🔍 Добавляю SEO...")
        try:
            html = site["files"].get("index.html", "")
            def call():
                return groq_call_with_html(SEO_PROMPT, html, "Добавь SEO оптимизацию.")
            raw = await asyncio.wait_for(asyncio.to_thread(call), timeout=65)
            files, summary = parse_json(raw)
            url = await asyncio.to_thread(deploy, files)
            push_history(files, url, site.get("name",""))
            save_site(site.get("name",""), url)
            await msg.edit_text(f"✅ SEO добавлен!\n\n🌐 {url}\n\n📝 {summary}", reply_markup=main_menu())
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}", reply_markup=main_menu())

    elif d == "qr":
        site = current_site()
        if not site:
            await q.edit_message_text("⚪ Нет сайта.", reply_markup=main_menu())
            return
        await q.message.reply_photo(photo=qr(site["url"]), caption=f"📱 QR-код:\n{site['url']}")
        await q.edit_message_text("Выбери действие:", reply_markup=main_menu())

    elif d == "undo":
        prev = pop_history()
        if not prev:
            await q.edit_message_text("⚪ Нет предыдущей версии.", reply_markup=main_menu())
            return
        msg = await q.edit_message_text("↩️ Откатываю...")
        try:
            url = await asyncio.to_thread(deploy, prev["files"])
            await msg.edit_text(f"✅ Откатил!\n\n🌐 {url}", reply_markup=main_menu())
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {str(e)[:200]}", reply_markup=main_menu())

    elif d == "list":
        sites = load_sites()
        if not sites:
            await q.edit_message_text("⚪ Сайтов ещё нет.", reply_markup=main_menu())
            return
        text = "📋 Твои сайты:\n\n"
        for s in reversed(sites[-10:]):
            text += f"• {s.get('name','Сайт')} ({s['date']})\n  {s['url']}\n\n"
        await q.edit_message_text(text, reply_markup=main_menu())

    elif d == "setstyle":
        context.user_data["state"] = "setstyle"
        await q.edit_message_text("📸 Отправь скриншот сайта — запомню стиль навсегда.")

    elif d == "clearstyle":
        if os.path.exists(STYLE_FILE): os.remove(STYLE_FILE)
        context.user_data["state"] = None
        await q.edit_message_text("🗑 Стиль сброшен.", reply_markup=main_menu())

    # Подтверждение брифа
    elif d == "confirm_yes":
        b = context.user_data.get("brief", {})
        name = b.get("name", "Сайт")
        brief_text = (f"Создай лендинг:\nНазвание: {name}\nОписание: {b.get('desc','')}\n"
                      f"Услуги: {b.get('services','')}\nКонтакты: {b.get('contacts','')}\n"
                      f"Стиль: {b.get('colors','тёмный премиальный')}\nДоп: {b.get('extras','нет')}\n"
                      f"Не оставляй заглушки — используй реальные данные везде.")
        context.user_data["state"] = None
        msg = await q.edit_message_text("🤖 Генерирую сайт (~20 сек)...")
        await do_generate(msg, name, brief_text, update)

    elif d == "confirm_no":
        context.user_data.update({"state": "new_q1", "brief": {}})
        await q.edit_message_text(QUESTIONS[0][1])


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    text  = update.message.text.strip()
    state = context.user_data.get("state")

    # Диалог создания сайта
    if state and state.startswith("new_q"):
        step = int(state[-1]) - 1  # 0..5
        key  = Q_KEYS[step]

        # Сохраняем ответ (если шаблон уже заполнил это поле — не перезаписываем если не нужно)
        context.user_data["brief"][key] = text

        if step < 5:
            next_state = f"new_q{step+2}"
            context.user_data["state"] = next_state
            _, question = QUESTIONS[step+1]
            if next_state == "new_q5":
                await update.message.reply_text(question, reply_markup=COLORS_KB)
            else:
                await update.message.reply_text(question, reply_markup=ReplyKeyboardRemove())
        else:
            # Все вопросы заданы — показываем бриф
            context.user_data["state"] = "confirm"
            b = context.user_data["brief"]
            confirm_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Создавай!", callback_data="confirm_yes"),
                InlineKeyboardButton("❌ Заново", callback_data="confirm_no")
            ]])
            await update.message.reply_text(
                f"✅ Проверь данные:\n\n"
                f"🏷 {b.get('name')}\n📝 {b.get('desc')}\n⚡ {b.get('services')}\n"
                f"📞 {b.get('contacts')}\n🎨 {b.get('colors')}\n➕ {b.get('extras')}\n\nВсё верно?",
                reply_markup=confirm_kb
            )
        return

    if state == "edit":
        context.user_data["state"] = None
        site = current_site()
        if not site:
            await update.message.reply_text("⚪ Нет сайта.", reply_markup=main_menu())
            return
        status = await update.message.reply_text("✏️ Вношу изменения...")
        try:
            html = site["files"].get("index.html","")
            def call():
                return groq_call_with_html(EDIT_PROMPT, html, f"ЧТО ИЗМЕНИТЬ: {text}")
            raw = await asyncio.wait_for(asyncio.to_thread(call), timeout=65)
            files, summary = parse_json(raw)
            url = await asyncio.to_thread(deploy, files)
            push_history(files, url, site.get("name",""))
            save_site(site.get("name",""), url)
            await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}", reply_markup=main_menu())
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {type(e).__name__}: {str(e)[:200]}", reply_markup=main_menu())
        return

    if state == "addblock":
        context.user_data["state"] = None
        site = current_site()
        if not site:
            await update.message.reply_text("⚪ Нет сайта.", reply_markup=main_menu())
            return
        status = await update.message.reply_text("➕ Добавляю раздел...")
        try:
            html = site["files"].get("index.html","")
            def call():
                return groq_call_with_html(ADD_PROMPT, html, f"ДОБАВИТЬ РАЗДЕЛ: {text}")
            raw = await asyncio.wait_for(asyncio.to_thread(call), timeout=65)
            files, summary = parse_json(raw)
            url = await asyncio.to_thread(deploy, files)
            push_history(files, url, site.get("name",""))
            save_site(site.get("name",""), url)
            await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}", reply_markup=main_menu())
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {type(e).__name__}: {str(e)[:200]}", reply_markup=main_menu())
        return

    # Без состояния — показываем меню
    await update.message.reply_text("Выбери действие:", reply_markup=main_menu())


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID: return
    if context.user_data.get("state") != "setstyle":
        await update.message.reply_text("Чтобы сохранить стиль — нажми «Сохранить стиль» в меню /start")
        return
    context.user_data["state"] = None
    photo = update.message.photo[-1]
    f     = await context.bot.get_file(photo.file_id)
    data  = await f.download_as_bytearray()
    b64   = base64.b64encode(bytes(data)).decode()
    status = await update.message.reply_text("🔍 Анализирую стиль...")
    try:
        def call():
            return groq_call([
                {"role": "system", "content": "Опиши стиль сайта: цвета hex, шрифты, отступы, кнопки, настроение."},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": "Опиши визуальный стиль детально."}
                ]}
            ], model="meta-llama/llama-4-scout-17b-16e-instruct", max_tokens=800)
        desc = await asyncio.wait_for(asyncio.to_thread(call), timeout=30)
        save_style(desc)
        await status.edit_text("✅ Стиль сохранён! Все сайты теперь в этом стиле.", reply_markup=main_menu())
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {str(e)[:200]}", reply_markup=main_menu())


async def error_handler(update, context):
    print(f"ERROR: {context.error}")
    if update and hasattr(update, "message") and update.message:
        try:
            await update.message.reply_text(f"❌ Ошибка: {str(context.error)[:200]}", reply_markup=main_menu())
        except: pass


async def post_init(app):
    await app.bot.set_my_commands([
        ("start", "Главное меню"),
        ("test",  "Проверить Groq API"),
    ])


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("test",  cmd_test))
    app.add_handler(CallbackQueryHandler(btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("✅ Бот запущен!")
    app.run_polling(drop_pending_updates=True)
