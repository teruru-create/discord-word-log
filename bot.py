import os
import datetime
import discord
from discord.ext import commands, tasks
import subprocess
import jaconv
import re
import asyncio
import json
from aiohttp import web
import requests

# ======================
# 設定
# ======================
TOKEN = os.environ.get("DISCORD_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

REPO_PATH = r"C:\Projects\discord-word-log"
CHANNEL_ID = 1123677033659109416
GUILD_ID = 865444542181933076

OUTPUT_FILE = os.path.join(REPO_PATH, "output.txt")
TAGS_FILE = os.path.join(REPO_PATH, "tags.json")
ADMIN_FILE = os.path.join(REPO_PATH, "admin.json")
VOTES_FILE = os.path.join(REPO_PATH, "votes.json")

# ======================
# トークンチェック
# ======================
if not TOKEN:
    print("ERROR: 環境変数 DISCORD_TOKEN が設定されていません")
    exit(1)

if not ANTHROPIC_API_KEY:
    print("ERROR: 環境変数 ANTHROPIC_API_KEY が設定されていません")
    exit(1)

TOKEN = TOKEN.strip()
if TOKEN.startswith("Bot "):
    TOKEN = TOKEN.split(" ", 1)[1]

# ======================
# Discord intents
# ======================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ======================
# 正規表現
# ======================
ALPHA_RE = re.compile(r"[A-Za-z]")
HIRAGANA_RE = re.compile(r"[\u3040-\u309F]")
KATAKANA_RE = re.compile(r"[\u30A0-\u30FF]")
KANJI_RE = re.compile(r"[\u4E00-\u9FFF]")

# ======================
# ひらがな・小文字に統一
# ======================
def normalize(text):
    t = text.strip()
    t = jaconv.kata2hira(t)
    t = t.lower()
    return t

# ======================
# カテゴリ分け
# ======================
def classify(text):
    if not text:
        return "other"
    ch = text[0]
    if ALPHA_RE.match(ch): return "alpha"
    if HIRAGANA_RE.match(ch) or KANJI_RE.match(ch): return "hiragana"
    if KATAKANA_RE.match(ch): return "katakana"
    return "other"

# ======================
# JSON 読み込み
# ======================
def load_json_file(filepath, default=None):
    if default is None:
        default = {}
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠ Error loading {filepath}: {e}")
    return default

# ======================
# JSON 保存
# ======================
def save_json_file(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"⚠ Error saving {filepath}: {e}")
        return False

# ======================
# TXT 出力
# ======================
def write_txt_from_map(normalized_map):
    groups = {"alpha": [], "hiragana": [], "katakana": [], "other": []}

    for v in normalized_map.values():
        cat = classify(v["raw"])
        groups[cat].append(v)

    for k in groups:
        groups[k] = sorted(groups[k], key=lambda x: normalize(x["raw"]))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=== LINES (unique, latest kept, sorted) ===\n")
        f.write(f"Updated: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n\n")

        for cat, title in [
            ("alpha", "A–Z"),
            ("hiragana", "ひらがな / 漢字"),
            ("katakana", "カタカナ"),
            ("other", "その他"),
        ]:
            if groups[cat]:
                f.write(f"--- {title} ---\n")
                for it in groups[cat]:
                    url = f"https://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}/{it['id']}"
                    f.write(f"{it['raw']:<40} | {it['date']} | {url} | {it['username']}\n")
                f.write("\n")

# ======================
# GitHub Push
# ======================
def push_to_github():
    try:
        subprocess.run(["git", "pull", "origin", "main"], cwd=REPO_PATH, check=False)
        subprocess.run(["git", "add", "."], cwd=REPO_PATH, check=False)

        result = subprocess.run(
            ["git", "commit", "-m", f"Auto update {datetime.datetime.now()}"],
            cwd=REPO_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )

        if "nothing to commit" in result.stdout:
            print("ℹ No updates to commit")
            return

        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_PATH, check=False)
        print("✅ GitHub updated")

    except Exception as e:
        print(f"⚠ GitHub push failed: {e}")

# ======================
# メッセージ取得 → TXT更新
# ======================
@tasks.loop(seconds=60)
async def fetch_and_save():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"ERROR: channel {CHANNEL_ID} not found")
        return

    normalized_map = {}

    try:
        print(f"Fetching messages...")
        async for msg in channel.history(limit=None, oldest_first=True):

            text = msg.content.strip()
            if not text:
                continue

            username = msg.author.display_name if msg.author else "Unknown"

            norm = normalize(text)
            entry = {
                "raw": text,
                "date": msg.created_at.strftime("%Y/%m/%d"),
                "id": msg.id,
                "username": username
            }

            if norm not in normalized_map or msg.id > normalized_map[norm]["id"]:
                normalized_map[norm] = entry

        if normalized_map:
            write_txt_from_map(normalized_map)

            # ❗ votes.json を破壊しない（投票バグ修正）
            if not os.path.exists(VOTES_FILE):
                save_json_file(VOTES_FILE, {"current": {}, "archive": []})

            print("Saving JSON files...")
            save_json_file(TAGS_FILE, load_json_file(TAGS_FILE, {}))
            save_json_file(ADMIN_FILE, load_json_file(ADMIN_FILE, {"hidden": [], "deleted": []}))
            # ❗ votes.json は上書きしない（Web → GitHub の内容をそのまま保持）
            print("Votes.json preserved (no overwrite)")

            push_to_github()
            print("✅ Update finished")

    except Exception as e:
        print(f"❌ Error in fetch loop: {e}")

@fetch_and_save.before_loop
async def before_loop():
    print("Waiting for bot ready...")
    await bot.wait_until_ready()

# ======================
# AI 生成 API (AIOHTTP)
# ======================
# ======================
# AI 生成 API (AIOHTTP + CORS対応)
# ======================
async def handle_generate(request):
    try:
        count = int(request.query.get("count", "5"))

        # output.txt 読み込み
        if not os.path.exists(OUTPUT_FILE):
            response = web.json_response({"messages": []})
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response

        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            lines = [
                line.split("|")[0].strip()
                for line in f.readlines()
                if "|" in line and not line.startswith("===")
            ]

        all_messages = "\n".join(lines)

        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1000,
            "messages": [{
                "role": "user",
                "content": f"""
以下の文章リストを学習して、同じ雰囲気で{count}個の新しい迷言を作ってください。
JSON形式: {{"messages": [".."]}}

{all_messages}
"""
            }]
        }

        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            }
        )

        data = r.json()

        # Claudeの返す structure に対応
        text = data["content"][0]["text"]
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)

        response = web.json_response(result)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    except Exception as e:
        response = web.json_response({"error": str(e)})
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

# OPTIONSリクエスト対応(プリフライト)
async def handle_options(request):
    response = web.Response()
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# ======================
# Bot起動 + APIサーバ起動
# ======================
async def start_web_app():
    app = web.Application()
    app.router.add_get("/generate", handle_generate)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("🌐 API server started at http://0.0.0.0:8080")

async def main():
    asyncio.create_task(start_web_app())
    fetch_and_save.start()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
