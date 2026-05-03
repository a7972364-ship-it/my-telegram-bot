import os, json, base64, re, requests
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TELEGRAM_TOKEN = "8651518107:AAFtxuF2KZDM4IeuGdf1bVb1_ZV01rcI5lk"
GROQ_KEY       = "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"
VERCEL_TOKEN   = os.environ.get("VERCEL_TOKEN", "")
MY_ID          = 311728841

client     = Groq(api_key=GROQ_KEY)
STYLE_FILE = "/tmp/saved_style.txt"
LAST_SITE  = "/tmp/last_site.json"  # сохраняем последний сайт

BASE_PROMPT = """Ты — топовый веб-дизайнер. Создавай визуально потрясающие сайты.

Формат ответа — ТОЛЬКО валидный JSON, никакого текста вне JSON:
{
  "files": {
    "index.html": "полный html код"
  },
  "summary": "1-2 предложения"
}

КРИТИЧЕСКИ ВАЖНО:
- ВЕСЬ CSS внутри тега <style> в <head> — никаких внешних файлов
- ВЕСЬ JS внутри тега <script> перед </body>
- Только внешние CDN через <script src="..."> и <link href="...">

ОБЯЗАТЕЛЬНЫЕ подключения в <head>:
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>

БАЗОВЫЕ СТИЛИ (всегда включай):
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { background: #0a0a0a; color: #ffffff; font-family: 'Inter', sans-serif; scroll-behavior: smooth; }

ДИЗАЙН:
- Акцент: градиент подобранный по теме сайта
- Карточки: background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px;
- Gradient text: background: linear-gradient(135deg, #X, #Y); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;

ОБЯЗАТЕЛЬНАЯ СТРУКТУРА:
1. Навбар fixed с backdrop-filter: blur(20px)
2. Hero 100vh с анимированным blob на фоне и большим gradient заголовком
3. Бегущая строка тегов (@keyframes marquee)
4. Секция преимуществ — сетка 3 карточки
5. Секция услуг
6. CTA с gradient фоном
7. Футер

КНОПКИ: border-radius:50px, gradient primary, transparent secondary
АНИМАЦИИ: IntersectionObserver fade-in для всех секций, blob animation"""

STYLE_ADDON = """

СОХРАНЁННЫЙ СТИЛЬ (применяй строго):
{style_description}"""

EDIT_PROMPT = """Ты — веб-разработчик. Тебе дан HTML код сайта и инструкция что изменить.

Внеси изменения и верни ТОЛЬКО валидный JSON:
{
  "files": {
    "index.html": "полный обновлённый html код"
  },
  "summary": "что именно изменил"
}

ВАЖНО:
- Сохраняй весь существующий дизайн, меняй только то что просят
- Весь CSS внутри <style>, весь JS внутри <script>
- Верни ПОЛНЫЙ html файл, не только изменённые части"""


# ─── Утилиты ─────────────────────────────────────────────────────────────────

def load_saved_style() -> str | None:
    if os.path.exists(STYLE_FILE):
        with open(STYLE_FILE, "r") as f:
            return f.read().strip()
    return None

def save_style(description: str):
    with open(STYLE_FILE, "w") as f:
        f.write(description)

def load_last_site() -> dict | None:
    if os.path.exists(LAST_SITE):
        with open(LAST_SITE, "r") as f:
            return json.load(f)
    return None

def save_last_site(files: dict, url: str):
    with open(LAST_SITE, "w") as f:
        json.dump({"files": files, "url": url}, f)

def build_system_prompt() -> str:
    style = load_saved_style()
    if style:
        return BASE_PROMPT + STYLE_ADDON.format(style_description=style)
    return BASE_PROMPT

def analyze_style(image_b64: str) -> str:
    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        max_tokens=1000,
        messages=[
            {"role": "system", "content": "Опиши визуальный стиль сайта на скриншоте: точные цвета (hex), шрифты, отступы, стиль кнопок, карточек, фона, анимации. Только описание."},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": "Опиши стиль максимально детально."}
            ]}
        ]
    )
    return response.choices[0].message.content.strip()

def parse_response(raw: str) -> tuple[dict, str]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    return data.get("files", {}), data.get("summary", "Готово!")

def deploy_to_vercel(files: dict) -> str:
    vercel_files = [
        {"file": name, "data": base64.b64encode(c.encode("utf-8")).decode("utf-8"), "encoding": "base64"}
        for name, c in files.items()
    ]
    resp = requests.post(
        "https://api.vercel.com/v13/deployments",
        headers={"Authorization": f"Bearer {VERCEL_TOKEN}", "Content-Type": "application/json"},
        data=json.dumps({"name": "my-telegram-sites", "files": vercel_files, "projectSettings": {"framework": None}}),
        timeout=60
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Vercel error {resp.status_code}: {resp.text[:300]}")
    url = resp.json().get("url", "")
    return ("https://" + url) if url and not url.startswith("http") else url


# ─── Генерация и деплой ──────────────────────────────────────────────────────

async def process_request(update: Update, user_text: str, image_b64: str | None = None):
    style = load_saved_style()
    status = await update.message.reply_text(
        ("🎨 Использую сохранённый стиль\n" if style else "") + "🤖 Создаю сайт..."
    )
    try:
        if image_b64:
            content = [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": user_text or "Создай сайт в стиле этого скриншота."}
            ]
            model = "meta-llama/llama-4-scout-17b-16e-instruct"
        else:
            content = user_text
            model   = "llama-3.3-70b-versatile"

        resp = client.chat.completions.create(
            model=model, max_tokens=8000,
            messages=[{"role": "system", "content": build_system_prompt()}, {"role": "user", "content": content}]
        )
        files, summary = parse_response(resp.choices[0].message.content)
        if not files:
            await status.edit_text("❌ Не удалось сгенерировать. Попробуй ещё раз.")
            return

        await status.edit_text("🚀 Деплою на Vercel...")
        url = deploy_to_vercel(files)
        save_last_site(files, url)

        await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}\n\nЧтобы изменить: /edit что изменить")
    except json.JSONDecodeError:
        await status.edit_text("❌ Ошибка формата. Попробуй ещё раз.")
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        raise


# ─── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    style = load_saved_style()
    last  = load_last_site()
    await update.message.reply_text(
        f"👋 Создаю премиальные сайты.\n\n"
        f"{'✅ Стиль сохранён' if style else '⚪ Стиль не задан'}\n"
        f"{'🌐 Последний сайт: ' + last['url'] if last else '⚪ Сайтов ещё нет'}\n\n"
        f"Команды:\n"
        f"/setstyle — сохранить стиль по скриншоту\n"
        f"/clearstyle — сбросить стиль\n"
        f"/edit [что изменить] — редактировать последний сайт\n"
        f"/last — ссылка на последний сайт"
    )

async def setstyle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text("📸 Отправь скриншот — запомню стиль навсегда.")
    context.user_data["waiting_for_style"] = True

async def clearstyle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if os.path.exists(STYLE_FILE):
        os.remove(STYLE_FILE)
    await update.message.reply_text("🗑 Стиль сброшен.")

async def last_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    site = load_last_site()
    if site:
        await update.message.reply_text(f"🌐 Последний сайт:\n{site['url']}")
    else:
        await update.message.reply_text("⚪ Сайтов ещё нет.")

async def edit_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    instruction = " ".join(context.args) if context.args else ""
    if not instruction:
        await update.message.reply_text("Напиши что изменить:\n/edit добавь форму обратной связи\n/edit измени цвет кнопок на золотой")
        return

    site = load_last_site()
    if not site:
        await update.message.reply_text("⚪ Нет сохранённого сайта. Сначала создай сайт.")
        return

    status = await update.message.reply_text("✏️ Вношу изменения...")
    try:
        html = site["files"].get("index.html", "")
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=8000,
            messages=[
                {"role": "system", "content": EDIT_PROMPT},
                {"role": "user", "content": f"HTML КОД САЙТА:\n{html}\n\nЧТО ИЗМЕНИТЬ: {instruction}"}
            ]
        )
        files, summary = parse_response(resp.choices[0].message.content)
        if not files:
            await status.edit_text("❌ Не удалось изменить. Попробуй ещё раз.")
            return

        await status.edit_text("🚀 Деплою обновлённый сайт...")
        url = deploy_to_vercel(files)
        save_last_site(files, url)

        await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}\n\nЧтобы ещё изменить: /edit что изменить")
    except json.JSONDecodeError:
        await status.edit_text("❌ Ошибка формата. Попробуй ещё раз.")
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        raise

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await process_request(update, update.message.text.strip())

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    photo     = update.message.photo[-1]
    file      = await context.bot.get_file(photo.file_id)
    content   = await file.download_as_bytearray()
    image_b64 = base64.b64encode(bytes(content)).decode("utf-8")

    if context.user_data.get("waiting_for_style"):
        context.user_data["waiting_for_style"] = False
        status = await update.message.reply_text("🔍 Анализирую стиль...")
        try:
            save_style(analyze_style(image_b64))
            await status.edit_text("✅ Стиль сохранён! Все сайты теперь в этом стиле.\n/clearstyle — сбросить.")
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {e}")
        return

    await process_request(update, update.message.caption or "", image_b64)


async def post_init(app):
    await app.bot.set_my_commands([
        ("start",      "Главная — статус и список команд"),
        ("setstyle",   "Сохранить стиль по скриншоту"),
        ("clearstyle", "Сбросить сохранённый стиль"),
        ("edit",       "Редактировать последний сайт"),
        ("last",       "Ссылка на последний сайт"),
    ])

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("setstyle",   setstyle))
    app.add_handler(CommandHandler("clearstyle", clearstyle))
    app.add_handler(CommandHandler("edit",       edit_site))
    app.add_handler(CommandHandler("last",       last_site))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("✅ Бот запущен!")
    app.run_polling()
