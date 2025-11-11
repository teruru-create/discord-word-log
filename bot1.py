import os
import datetime
import discord
from discord.ext import commands, tasks
import subprocess
import jaconv
import re

# ===== 環境変数からトークン取得 =====
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    print("ERROR: DISCORD_TOKEN 環境変数が設定されていません")
    exit(1)

TOKEN = TOKEN.strip()
if TOKEN.startswith("Bot "):
    TOKEN = TOKEN.split(" ", 1)[1]

# ===== ローカル GitHub リポジトリ情報 =====
REPO_PATH = r"C:\Projects\discord-word-log"
CHANNEL_ID = 1123677033659109416  # ここにチャンネルID or スレッドID
OUTPUT_FILE = os.path.join(REPO_PATH, "output.txt")

# ===== Discord Bot 設定 =====
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== 正規表現とデータ保存 =====
ALPHA_RE = re.compile(r"[A-Za-z]")
HIRAGANA_RE = re.compile(r"[\u3040-\u309F]")
KATAKANA_RE = re.compile(r"[\u30A0-\u30FF]")
KANJI_RE = re.compile(r"[\u4E00-\u9FFF]")

data = {}  # key: normalized, value: {"raw": text, "date": "YYYY/MM/DD"}
last_message_id = None

# ===== ヘルパー =====
def normalize(text):
    t = text.strip()
    t = jaconv.kata2hira(t)
    t = t.lower()
    return t

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

def write_txt():
    groups = {"alpha": [], "hiragana": [], "katakana": [], "other": []}
    for item in data.values():
        cat = classify(item["raw"])
        groups[cat].append(item)
    for k in groups:
        groups[k] = sorted(groups[k], key=lambda x: x["raw"].lower())

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=== LINES (unique, sorted) ===\n")
        f.write(f"Updated: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n\n")
        for cat, title in [("alpha", "A–Z"), ("hiragana", "あ〜（ひらがな/漢字）"), ("katakana", "ア〜（カタカナ）"), ("other", "その他")]:
            if groups[cat]:
                f.write(f"--- {title} ---\n")
                for it in groups[cat]:
                    f.write(f"{it['raw']:<20} | {it['date']}\n")
                f.write("\n")

def push_to_github():
    try:
        git_dir = os.path.join(REPO_PATH, '.git')
        # rebase中はスキップ
        if os.path.exists(os.path.join(git_dir, 'rebase-apply')) or os.path.exists(os.path.join(git_dir, 'rebase-merge')):
            print("Git rebase中のため push をスキップ")
            return

        # add + commit
        subprocess.run(["git", "add", "output.txt"], cwd=REPO_PATH, check=True)
        subprocess.run(["git", "commit", "-m", f"Update output.txt {datetime.datetime.now()}"], cwd=REPO_PATH, check=False)

        # pullしてリモートを統合（rebase）
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=REPO_PATH, check=False)

        # push
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_PATH, check=False)
        print("GitHub updated successfully")
    except Exception as e:
        print(f"Git操作失敗: {e}")

# ===== メイン処理 =====
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    fetch_and_save.start()

@tasks.loop(seconds=60)
async def fetch_and_save():
    global last_message_id
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found")
        return

    try:
        after_param = discord.Object(last_message_id) if last_message_id else None
        
        async for msg in channel.history(limit=100, oldest_first=True, after=after_param):
            key = msg.content.strip()
            if key:
                normalized = normalize(key)
                data[normalized] = {"raw": key, "date": msg.created_at.strftime("%Y/%m/%d")}
            last_message_id = msg.id

        if data:
            write_txt()
            push_to_github()

    except Exception as e:
        print(f"Error in fetch_and_save: {e}")

# ===== Bot起動 =====
try:
    bot.run(TOKEN)
except discord.errors.LoginFailure:
    print("ERROR: Discord トークンが無効です")
    exit(1)
