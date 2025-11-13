import os
import datetime
import discord
from discord.ext import commands, tasks
import subprocess
import jaconv
import re
import asyncio
import json

# ======================
# 設定
# ======================
TOKEN = os.environ.get("DISCORD_TOKEN")
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
    if ALPHA_RE.match(ch):
        return "alpha"
    if HIRAGANA_RE.match(ch) or KANJI_RE.match(ch):
        return "hiragana"
    if KATAKANA_RE.match(ch):
        return "katakana"
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
# TXT 出力(ユーザー名付き)
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
                    # フォーマット: メッセージ | 日付 | URL | ユーザー名
                    f.write(f"{it['raw']:<40} | {it['date']} | {url} | {it['username']}\n")
                f.write("\n")

# ======================
# GitHub Push
# ======================
def push_to_github():
    """
    output.txt, tags.json, admin.json, votes.json を GitHub に push する。
    """
    try:
        # Git pull して最新状態にする
        subprocess.run(["git", "pull", "origin", "main"], cwd=REPO_PATH, check=False)
        
        # 変更をステージ
        subprocess.run(["git", "add", "output.txt", "tags.json", "admin.json", "votes.json"], 
                      cwd=REPO_PATH, check=False)

        # commit 
        result = subprocess.run(
            ["git", "commit", "-m", f"Update files {datetime.datetime.now()}"],
            cwd=REPO_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )

        # 変更がない場合はスキップ
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            print("ℹ️ No changes to commit")
            return

        # push
        push_result = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=REPO_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )

        if push_result.returncode == 0:
            print("✅ GitHub updated")
        else:
            print("⚠ GitHub push failed (ignored):")
            print(push_result.stderr.strip())

    except Exception as e:
        print(f"⚠ GitHub push failed (ignored): {e}")

# ======================
# Discord → TXT更新処理
# ======================
@tasks.loop(seconds=60)
async def fetch_and_save():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"ERROR: channel {CHANNEL_ID} not found")
        return

    normalized_map = {}

    try:
        print(f"Fetching messages from channel {CHANNEL_ID}...")
        message_count = 0
        
        async for msg in channel.history(limit=None, oldest_first=True):
            message_count += 1
            text = msg.content.strip()
            if not text:
                continue

            # ユーザー名取得
            username = msg.author.display_name if msg.author else "Unknown"

            norm = normalize(text)
            entry = {
                "raw": text,
                "date": msg.created_at.strftime("%Y/%m/%d"),
                "id": msg.id,
                "username": username
            }

            if norm in normalized_map:
                if msg.id > normalized_map[norm]["id"]:
                    normalized_map[norm] = entry
            else:
                normalized_map[norm] = entry

        print(f"Fetched {message_count} messages, {len(normalized_map)} unique entries")

        if normalized_map:
            write_txt_from_map(normalized_map)
            
            # 各JSONファイルが存在しない場合は空ファイルを作成
            if not os.path.exists(TAGS_FILE):
                save_json_file(TAGS_FILE, {})
            if not os.path.exists(ADMIN_FILE):
                save_json_file(ADMIN_FILE, {"hidden": [], "deleted": []})
            if not os.path.exists(VOTES_FILE):
                save_json_file(VOTES_FILE, {"current": {}, "archive": []})
            
            # Webからの変更をマージ（今回は既存データを保持）
            existing_tags = load_json_file(TAGS_FILE, {})
            existing_admin = load_json_file(ADMIN_FILE, {"hidden": [], "deleted": []})
            existing_votes = load_json_file(VOTES_FILE, {"current": {}, "archive": []})
            
            # 既存データを再保存（Webからの変更は手動でJSONを編集する必要があります）
            save_json_file(TAGS_FILE, existing_tags)
            save_json_file(ADMIN_FILE, existing_admin)
            save_json_file(VOTES_FILE, existing_votes)
            
            push_to_github()
            print(f"✅ Successfully wrote {len(normalized_map)} unique entries")
        else:
            print("⚠️ No messages found or normalized_map empty")

    except discord.errors.Forbidden as e:
        print(f"❌ Permission Error: Bot doesn't have access to channel. Error: {e}")
    except discord.errors.HTTPException as e:
        print(f"❌ Discord API Error: {e}, retrying in 5s...")
        await asyncio.sleep(5)
    except Exception as e:
        print(f"❌ Error in fetch_and_save: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

# タスク開始前に準備完了を待つ
@fetch_and_save.before_loop
async def before_fetch_and_save():
    print("Waiting for bot to be ready...")
    await bot.wait_until_ready()
    print("Bot is ready, starting fetch_and_save task")

# ======================
# Bot準備完了
# ======================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} guild(s)")
    
    # チャンネルの存在確認
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        print(f"✅ Target channel found: {channel.name}")
    else:
        print(f"❌ ERROR: Channel {CHANNEL_ID} not found!")
    
    # タスクがまだ開始されていない場合のみ開始
    if not fetch_and_save.is_running():
        fetch_and_save.start()

# ======================
# エラーハンドリング
# ======================
@bot.event
async def on_error(event, *args, **kwargs):
    print(f"❌ Error in {event}:")
    import traceback
    traceback.print_exc()

# ======================
# Bot Run
# ======================
try:
    bot.run(TOKEN)
except discord.errors.LoginFailure:
    print("❌ ERROR: Invalid token. Please check DISCORD_TOKEN environment variable")
except Exception as e:
    print(f"❌ ERROR: Failed to start bot: {e}")
    import traceback
    traceback.print_exc()
