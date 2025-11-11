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
def write_txt_from_map(normalized_map):
    groups = {"alpha": [], "hiragana": [], "katakana": [], "other": []}
    for v in normalized_map.values():
        cat = classify(v["raw"])
        groups[cat].append(v)

    for k in groups:
        groups[k] = sorted(groups[k], key=lambda x: normalize(x["raw"]))

    # ここから追加
    DISCORD_MSG_BASE_URL = f"https://discord.com/channels/@me/{CHANNEL_ID}/"

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
                    # ここで URL を作る
                    url = f"{DISCORD_MSG_BASE_URL}{it['id']}"
                    # 元の raw と日付に加えて URL を書き込む
                    f.write(f"{it['raw']:<40} | {it['date']} | {url}\n")
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
    """
    毎分チャンネル全履歴を読み、normalized をキーに最新メッセージのみ保持して output.txt を作る。
    重要: 毎回辞書を再構築するため、二重追加・増え続ける問題を防げます。
    """
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("ERROR: channel not found")
        return

    normalized_map = {}  # キー: normalize(text) -> 値: {"raw": original, "date": YYYY/MM/DD, "id": msg.id}

    try:
        # 全履歴を取得（必要に応じて limit=None を適宜調整）
        async for msg in channel.history(limit=None, oldest_first=True):
            text = msg.content.strip()
            if not text:
                continue

            norm = normalize(text)  # 例: カタカナ→ひらがな、小文字化など
            entry = {
                "raw": text,
                "date": msg.created_at.strftime("%Y/%m/%d"),
                "id": msg.id
            }

            # 既存がなければ入れる。あれば「より新しいもの」を残す（created_at または id で比較）
            if norm in normalized_map:
                # 比較方法：メッセージID は Snowflake で増加するので id を比較することで新旧判定ができる
                if msg.id > normalized_map[norm]["id"]:
                    normalized_map[norm] = entry
            else:
                normalized_map[norm] = entry

        # 書き込み & push
        if normalized_map:
            write_txt_from_map(normalized_map)
            push_to_github()
            print(f"fetch_and_save: wrote {len(normalized_map)} unique entries")
        else:
            print("fetch_and_save: no messages found or normalized_map empty")

    except Exception as e:
        print(f"Error in fetch_and_save: {e}")

# ======================
# Bot Run
# ======================
bot.run(TOKEN)


