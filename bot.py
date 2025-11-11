import os
import datetime
import discord
from discord.ext import commands, tasks
import subprocess
import jaconv
import re

# トークン取得（必ず環境変数から）
TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    print("ERROR: DISCORD_TOKEN 環境変数が設定されていません")
    print("修正方法:")
    print("  1. Discord Developer Portal から有効なボットトークンを取得")
    print("  2. 以下のコマンドでボットを実行:")
    print("     $env:DISCORD_TOKEN='ここにトークンを貼り付け'; python bot.py")
    exit(1)

# トークンのサニタイズ（余分なクォートや 'Bot ' プレフィックスを削除）
TOKEN = TOKEN.strip()
if (TOKEN.startswith("'") and TOKEN.endswith("'")) or (TOKEN.startswith('"') and TOKEN.endswith('"')):
    TOKEN = TOKEN[1:-1]
if TOKEN.startswith("Bot "):
    TOKEN = TOKEN.split(" ", 1)[1]

# セーフな診断情報（トークン本体は表示しない）
def _safe_token_info(t):
    try:
        return f"length={len(t)}, start={t[:4]}, end={t[-4:]}"
    except Exception:
        return "(could not read token)"

print(f"DISCORD_TOKEN info: {_safe_token_info(TOKEN)}")
if " " in TOKEN or len(TOKEN) < 50:
    print("ERROR: DISCORD_TOKEN の形式が不正な可能性があります。トークンを再確認してください。")
    exit(1)

REPO_PATH = r"C:\Projects\discord-word-log"
CHANNEL_ID = 1123677033659109416
OUTPUT_FILE = os.path.join(REPO_PATH, "output.txt")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 文字分類 ---
ALPHA_RE = re.compile(r"[A-Za-z]")
HIRAGANA_RE = re.compile(r"[\u3040-\u309F]")
KATAKANA_RE = re.compile(r"[\u30A0-\u30FF]")
KANJI_RE = re.compile(r"[\u4E00-\u9FFF]")

# 保存データ
data = {}  # key: normalized, value: {"raw": text, "date": "YYYY/MM/DD"}
last_message_id = None  # 最後に処理したメッセージID


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
        if os.path.exists(os.path.join(git_dir, 'rebase-apply')) or os.path.exists(os.path.join(git_dir, 'rebase-merge')):
            print('Git 状態: rebase が進行中のため commit/push をスキップします。手動で rebase を完了してください。')
            return
        subprocess.run(["git", "add", "output.txt"], cwd=REPO_PATH, check=True)
        subprocess.run(["git", "commit", "-m", f"Update output.txt {datetime.datetime.now()}"], cwd=REPO_PATH, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_PATH, check=True)
        print("GitHub updated successfully")
    except subprocess.CalledProcessError as e:
        print(f"GitHub push failed: {e}")
    except Exception as e:
        print(f"Git operation failed: {e}")


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
        # after パラメータを安全に設定
        after_param = None
        if last_message_id:
            after_param = discord.Object(last_message_id)
        
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


try:
    bot.run(TOKEN)
except discord.errors.LoginFailure:
    print("ERROR: Discord トークンが無効です")
    print("修正方法:")
    print("  1. Discord Developer Portal (https://discord.com/developers/applications) にアクセス")
    print("  2. ボットアプリケーションを選択")
    print("  3. 左側の 'TOKEN' をクリック")
    print("  4. 'Copy' ボタンをクリックして新しいトークンをコピー")
    print("  5. 以下のコマンドで実行:")
    print("     $env:DISCORD_TOKEN='新しいトークン'; python bot.py")
    exit(1)

