import os
import datetime
import discord
from discord.ext import commands, tasks
import subprocess
import jaconv
import re

# ======================
# 設定
# ======================
TOKEN = os.environ.get("DISCORD_TOKEN")
REPO_PATH = r"C:\Projects\discord-word-log"
CHANNEL_ID = 1123677033659109416
OUTPUT_FILE = os.path.join(REPO_PATH, "output.txt")

# ======================
# トークンチェック
# ======================
if not TOKEN:
    print("ERROR: 環境変数 DISCORD_TOKEN が設定されていません")
    exit(1)

TOKEN = TOKEN.strip()
if TOKEN.startswith("Bot "):
    TOKEN = TOKEN.split(" ", 1)[1]


# ======================
# Discord intents
# ======================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ======================
# 正規表現
# ======================
ALPHA_RE = re.compile(r"[A-Za-z]")
HIRAGANA_RE = re.compile(r"[\u3040-\u309F]")
KATAKANA_RE = re.compile(r"[\u30A0-\u30FF]")
KANJI_RE = re.compile(r"[\u4E00-\u9FFF]")

# ======================
# データ保持（normalize を廃止 → 重複保持）
# ======================
all_lines = []   # {raw, date} を全部保持


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
    if ALPHA_RE.match(ch):
        return "alpha"
    if HIRAGANA_RE.match(ch) or KANJI_RE.match(ch):
        return "hiragana"
    if KATAKANA_RE.match(ch):
        return "katakana"
    return "other"


# ======================
# TXT 出力
# ======================
def write_txt():
    groups = {"alpha": [], "hiragana": [], "katakana": [], "other": []}

    for item in all_lines:
        cat = classify(item["raw"])
        groups[cat].append(item)

    # 並べ替え
    for k in groups:
        groups[k] = sorted(groups[k], key=lambda x: normalize(x["raw"]))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=== LINES (sorted) ===\n")
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
                    f.write(f"{it['raw']:<20} | {it['date']}\n")
                f.write("\n")


# ======================
# GitHub Push
# ======================
def push_to_github():
    try:
        subprocess.run(["git", "add", "output.txt"], cwd=REPO_PATH, check=True)

        subprocess.run(
            ["git", "commit", "-m", f"Update output.txt {datetime.datetime.now()}"],
            cwd=REPO_PATH, check=False
        )

        subprocess.run(["git", "pull", "--rebase"], cwd=REPO_PATH, check=False)

        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=REPO_PATH, check=False
        )

        print("✅ GitHub updated")
    except Exception as e:
        print(f"⚠ GitHub push failed: {e}")


# ======================
# Bot準備完了
# ======================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    fetch_and_save.start()


# ======================
# Discord → TXT更新処理
# ======================
@tasks.loop(seconds=60)
async def fetch_and_save():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("ERROR: channel not found")
        return

    try:
        # ★ 全履歴取得 (limit=None)
        async for msg in channel.history(limit=None, oldest_first=True):
            text = msg.content.strip()
            if not text:
                continue

            entry = {
                "raw": text,
                "date": msg.created_at.strftime("%Y/%m/%d")
            }
            all_lines.append(entry)

        # 書き込み & GitHub反映
        write_txt()
        push_to_github()

    except Exception as e:
        print(f"Error in fetch_and_save: {e}")


# ======================
# Bot Run
# ======================
bot.run(TOKEN)

