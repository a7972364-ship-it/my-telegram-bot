import os, json, base64, re, time, requests
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TELEGRAM_TOKEN = "8651518107:AAFtxuF2KZDM4IeuGdf1bVb1_ZV01rcI5lk"
GROQ_KEY       = "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"
VERCEL_TOKEN   = os.environ.get("VERCEL_TOKEN", "")
MY_ID          = 311728841

client = Groq(api_key=GROQ_KEY)

# Путь где сохраняется стиль-референс
STYLE_FILE = "/tmp/saved_style.txt"

BASE_PROMPT = """Ты — топовый веб-дизайнер. Создавай визуально потрясающие сайты.

Формат ответа — ТОЛЬКО валидный JSON без лишнего текста:
{
  "files": {
    "index.html": "полный код"
  },
  "summary": "1-2 предложения что сделал"
}

ДИЗАЙН — строго следуй:

ЦВЕТА:
- Фон: почти чёрный #0a0a0a или #080808
- Акцент: яркий градиент по теме
- Текст: белый #ffffff и серый #888888
- Карточки: rgba(255,255,255,0.04) с border: 1px solid rgba(255,255,255,0.08)

ТИПОГРАФИКА:
- <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
- Заголовок hero: 72-96px, font-weight 800-900, letter-spacing -2px
- Gradient text: background: linear-gradient(...); -webkit-background-clip: text; -webkit-text-fill-color: transparent;

СТРУКТУРА:
1. Sticky навбар с backdrop-filter: blur(20px)
2. Hero на весь экран с анимированным gradient blob на фоне
3. Бегущая строка тегов (marquee CSS анимация)
4. Секция преимуществ — сетка карточек
5. Секция услуг
6. CTA с градиентным фоном
7. Футер

АНИМАЦИИ:
- <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
- Blob: filter: blur(120px); opacity: 0.15; CSS keyframes анимация
- IntersectionObserver для fade-in элементов при скролле
- Hover эффекты на кнопках и карточках"""

STYLE_ADDON = """

ВАЖНО: У тебя есть сохранённый стиль-референс от пользователя (описание ниже).
Строго следуй этому стилю — цвета, типографика, отступы, компоненты, настроение.
Применяй его к любому новому сайту независимо от тематики.

СОХРАНЁННЫЙ СТИЛЬ:
{style_description}"""


def load_saved_style() -> str | None:
    """Загружает сохранённое описание стиля."""
    if os.path.exists(STYLE_FILE):
        with open(STYLE_FILE, "r") as f:
            return f.read().strip()
    return None


def save_style(description: str):
    """Сохраняет описание стиля."""
    with open(STYLE_FILE, "w") as f:
        f.write(description)


def analyze_style(image_b64: str) -> str:
    """Просит Groq проанализировать скриншот и описать стиль."""
    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        max_tokens=1000,
        messages=[
            {
                "role": "system",
                "content": "Ты — дизайнер. Проанализируй скриншот сайта и опиши его визуальный стиль детально: цветовая палитра (точные цвета), типографика, отступы, стиль кнопок, карточек, фона, анимации, общее настроение. Отвечай только описанием стиля, без лишних слов."
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": "Опиши визуальный стиль этого сайта максимально детально."}
                ]
            }
        ]
    )
    return response.choices[0].message.content.strip()


def build_system_prompt() -> str:
    """Строит промпт с учётом сохранённого стиля."""
    style = load_saved_style()
    if style:
        return BASE_PROMPT + STYLE_ADDON.format(style_description=style)
    return BASE_PROMPT


def generate_site_files(user_text: str, image_b64: str | None = None) -> tuple[dict[str, str], str]:
    system = build_system_prompt()

    if image_b64:
        content = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            {"type": "text", "text": user_text or "Создай сайт используя стиль с этого скриншота."}
        ]
        model = "meta-llama/llama-4-scout-17b-16e-instruct"
    else:
        content = user_text
        model   = "llama-3.3-70b-versatile"

    response = client.chat.completions.create(
        model=model,
        max_tokens=8000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": content}
        ]
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data  = json.loads(raw)
    return data.get("files", {}), data.get("summary", "Сайт готов!")


def deploy_to_vercel(files: dict[str, str]) -> str:
    vercel_files = [
        {
            "file": name,
            "data": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "encoding": "base64"
        }
        for name, content in files.items()
    ]
    resp = requests.post(
        "https://api.vercel.com/v13/deployments",
        headers={"Authorization": f"Bearer {VERCEL_TOKEN}", "Content-Type": "application/json"},
        data=json.dumps({
            "name": "my-telegram-sites",
            "files": vercel_files,
            "projectSettings": {"framework": None}
        }),
        timeout=60
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Vercel error {resp.status_code}: {resp.text[:300]}")
    url = resp.json().get("url", "")
    return ("https://" + url) if url and not url.startswith("http") else url


# ─── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    style = load_saved_style()
    style_status = "✅ Стиль сохранён" if style else "⚪ Стиль не задан (используется стандартный)"
    await update.message.reply_text(
        "👋 Создаю премиальные сайты и деплою на Vercel.\n\n"
        f"{style_status}\n\n"
        "Команды:\n"
        "/setstyle — отправь скриншот сайта чтобы запомнить стиль\n"
        "/clearstyle — сбросить сохранённый стиль\n\n"
        "Просто пиши что нужно сделать:",
        parse_mode=None
    )


async def setstyle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text(
        "📸 Отправь скриншот сайта стиль которого хочешь сохранить.\n"
        "Все следующие сайты будут делаться в этом стиле."
    )
    context.user_data["waiting_for_style"] = True


async def clearstyle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if os.path.exists(STYLE_FILE):
        os.remove(STYLE_FILE)
    await update.message.reply_text("🗑 Стиль сброшен. Буду использовать стандартный дизайн.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    user_text = update.message.text.strip()
    if not user_text:
        return

    style = load_saved_style()
    style_note = "🎨 Использую сохранённый стиль\n" if style else ""

    status = await update.message.reply_text(f"{style_note}🤖 Создаю сайт...")
    try:
        files, summary = generate_site_files(user_text)
        if not files:
            await status.edit_text("❌ Не удалось сгенерировать. Попробуй ещё раз.")
            return
        await status.edit_text(f"{style_note}🚀 Деплою на Vercel...")
        url = deploy_to_vercel(files)
        await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}")
    except json.JSONDecodeError:
        await status.edit_text("❌ Ошибка формата. Попробуй ещё раз.")
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        raise


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    photo     = update.message.photo[-1]
    file      = await context.bot.get_file(photo.file_id)
    content   = await file.download_as_bytearray()
    image_b64 = base64.b64encode(bytes(content)).decode("utf-8")
    caption   = update.message.caption or ""

    # Если ждём стиль — сохраняем
    if context.user_data.get("waiting_for_style"):
        context.user_data["waiting_for_style"] = False
        status = await update.message.reply_text("🔍 Анализирую стиль...")
        try:
            description = analyze_style(image_b64)
            save_style(description)
            await status.edit_text(
                f"✅ Стиль сохранён!\n\n"
                f"Теперь все сайты будут делаться в этом стиле.\n"
                f"Чтобы сбросить — /clearstyle"
            )
        except Exception as e:
            await status.edit_text(f"❌ Ошибка анализа: {e}")
        return

    # Иначе — генерируем сайт с этим фото как референсом
    style = load_saved_style()
    style_note = "🎨 + сохранённый стиль\n" if style else ""
    status = await update.message.reply_text(f"🔍 Анализирую скриншот...{style_note}")
    try:
        files, summary = generate_site_files(caption, image_b64)
        if not files:
            await status.edit_text("❌ Не удалось сгенерировать. Попробуй ещё раз.")
            return
        await status.edit_text("🚀 Деплою на Vercel...")
        url = deploy_to_vercel(files)
        await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}")
    except json.JSONDecodeError:
        await status.edit_text("❌ Ошибка формата. Попробуй ещё раз.")
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        raise


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setstyle", setstyle))
    app.add_handler(CommandHandler("clearstyle", clearstyle))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("✅ Бот запущен!")
    app.run_polling()
