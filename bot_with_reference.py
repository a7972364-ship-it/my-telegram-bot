"""
Telegram Bot — генерирует сайты через Gemini и деплоит на Vercel.
Поддерживает референсы: просто кинь ссылку на сайт который нравится.

Установка:
    pip install google-generativeai python-telegram-bot requests

Примеры использования в Telegram:
    "Сделай лендинг для кофейни"
    "https://stripe.com  —  сделай похожий стиль, но для портфолио"
    "https://linear.app"  (без описания — скопирует общий стиль)
"""

import os, json, base64, re, time, requests
import google.generativeai as genai
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# ─── Конфигурация ────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = "8651518107:AAFtxuF2KZDM4IeuGdf1bVb1_ZV01rcI5lk"
GEMINI_KEY     = "AIzaSyBvlgIea9aDUEqg77tEqzMVQtbZNkHwOk0"
VERCEL_TOKEN   = "vcp_0RK0qObXsHx0QLrscLH0fAbpzJdfnxwkzCQLudCFy3na0zw2Qj29KfDY"
# ─────────────────────────────────────────────────────────────────────────────

genai.configure(api_key=GEMINI_KEY)

URL_REGEX = re.compile(r'https?://[^\s]+', re.IGNORECASE)

CREATE_FILE_TOOL = genai.protos.Tool(
    function_declarations=[
        genai.protos.FunctionDeclaration(
            name="create_file",
            description="Создаёт файл сайта. Вызывай отдельно для каждого файла.",
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    "filename": genai.protos.Schema(
                        type=genai.protos.Type.STRING,
                        description="index.html, style.css или script.js"
                    ),
                    "content": genai.protos.Schema(
                        type=genai.protos.Type.STRING,
                        description="Полное содержимое файла"
                    ),
                },
                required=["filename", "content"]
            )
        )
    ]
)

SYSTEM_BASE = """Ты — опытный веб-разработчик. Создавай файлы через инструмент create_file.

Правила:
- Всегда создавай index.html
- Добавляй style.css и script.js если нужно, подключай через относительные пути
- Пиши красивый, современный, адаптивный код
- Не используй внешние CDN — весь код в файлах
- После создания файлов напиши 1-2 предложения что сделал"""

SYSTEM_WITH_REF = SYSTEM_BASE + """

Тебе будет показан скриншот референсного сайта. Проанализируй его визуальный стиль:
цветовую палитру, типографику, отступы, компоненты, общее настроение — и воспроизведи
этот стиль в новом сайте. Не копируй содержимое — только дизайн."""


def get_screenshot_bytes(url: str) -> bytes | None:
    """Делает скриншот сайта через бесплатный API (без ключа)."""
    # thum.io — полностью бесплатный, без регистрации
    screenshot_url = f"https://image.thum.io/get/width/1280/crop/900/{url}"
    try:
        r = requests.get(screenshot_url, timeout=20)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            return r.content
    except Exception:
        pass
    return None


def extract_urls(text: str) -> list[str]:
    return URL_REGEX.findall(text)


def build_prompt(user_text: str, has_ref: bool) -> str:
    urls = extract_urls(user_text)
    clean_text = URL_REGEX.sub("", user_text).strip(" —-\n")

    if has_ref and not clean_text:
        return "Проанализируй стиль на скриншоте и создай новый сайт в таком же стиле. Придумай подходящий контент."
    elif has_ref and clean_text:
        return f"Проанализируй стиль на скриншоте. Создай сайт в этом стиле: {clean_text}"
    else:
        return user_text


def generate_site_files(user_text: str, screenshot: bytes | None = None) -> tuple[dict[str, str], str]:
    """Запускает agentic loop с Gemini, собирает файлы."""
    has_ref = screenshot is not None
    system  = SYSTEM_WITH_REF if has_ref else SYSTEM_BASE

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=system,
        tools=[CREATE_FILE_TOOL]
    )

    prompt_text = build_prompt(user_text, has_ref)

    # Формируем первое сообщение — текст + скриншот (если есть)
    if screenshot:
        first_message = [
            {"mime_type": "image/jpeg", "data": screenshot},
            prompt_text
        ]
    else:
        first_message = prompt_text

    files: dict[str, str] = {}
    chat     = model.start_chat()
    response = chat.send_message(first_message)

    # Agentic loop
    while True:
        tool_responses = []
        text_parts     = []

        for part in response.parts:
            if fn := part.function_call:
                filename = fn.args.get("filename", "")
                content  = fn.args.get("content", "")
                if filename and content:
                    files[filename] = content
                tool_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fn.name,
                            response={"result": f"Файл '{filename}' создан."}
                        )
                    )
                )
            elif part.text and part.text.strip():
                text_parts.append(part.text.strip())

        if tool_responses:
            response = chat.send_message(tool_responses)
        else:
            break

    summary = "\n".join(text_parts) if text_parts else "Сайт готов!"
    return files, summary


def deploy_to_vercel(files: dict[str, str], project_name: str) -> str:
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
        data=json.dumps({"name": project_name, "files": vercel_files, "projectSettings": {"framework": None}}),
        timeout=60
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Vercel error {resp.status_code}: {resp.text[:300]}")
    url = resp.json().get("url", "")
    return ("https://" + url) if url and not url.startswith("http") else url


def make_project_name(text: str) -> str:
    slug   = re.sub(r"[^a-z0-9]+", "-", text.lower())[:28].strip("-")
    suffix = int(time.time()) % 10000
    return f"tg-{slug}-{suffix}" if slug else f"tg-site-{suffix}"


# ─── Telegram handlers ───────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я создаю сайты и деплою их на Vercel.\n\n"
        "Как использовать:\n"
        "• Просто опиши сайт: _Лендинг для кофейни с тёмной темой_\n"
        "• Кинь ссылку-референс: _https://stripe.com_\n"
        "• Или вместе: _https://linear.app — сделай похожее для агентства_",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    if not user_text:
        return

    urls       = extract_urls(user_text)
    has_ref    = bool(urls)
    screenshot = None

    status = await update.message.reply_text("⏳ Начинаю...")

    try:
        # Если есть URL — делаем скриншот
        if has_ref:
            await status.edit_text(f"📸 Делаю скриншот {urls[0]}...")
            screenshot = get_screenshot_bytes(urls[0])
            if not screenshot:
                await status.edit_text("⚠️ Не смог сделать скриншот, генерирую без референса...")

        await status.edit_text("🤖 Gemini анализирует и пишет код...")
        files, summary = generate_site_files(user_text, screenshot)

        if not files:
            await status.edit_text("❌ Не удалось сгенерировать файлы. Попробуй переформулировать.")
            return

        file_list = ", ".join(files.keys())
        await status.edit_text(f"🚀 Деплою на Vercel ({file_list})...")

        url = deploy_to_vercel(files, make_project_name(user_text))

        ref_note = f"🎨 Референс: {urls[0]}\n" if has_ref and screenshot else ""
        await status.edit_text(
            f"✅ Готово!\n\n"
            f"🌐 {url}\n\n"
            f"{ref_note}"
            f"📝 {summary}\n\n"
            f"📁 Файлы: {file_list}"
        )

    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        raise


# ─── Запуск ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Бот запущен! Пиши в Telegram.")
    app.run_polling()
