import os
import datetime
import discord
from discord.ext import commands
from git import Repo
import jaconv
import re

TOKEN = os.environ.get("DISCORD_TOKEN")

REPO_PATH = r"C:\Projects\discord-word-log"
TXT_FILE = os.path.join(REPO_PATH, "output.txt")

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

def normalize(text):
    t = text.strip()
    t = jaconv.kata2hira(t)      # カタカナ→ひらがな
    t = t.lower()                # 小文字化
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
    # ソート
    for k in groups:
        groups[k] = sorted(groups[k], key=lambda x: x["raw"].lower())
    # 出力
    with open(TXT_FILE, "w", encoding="utf-8") as f:
        f.write("📘 Discord Word Log\n")
        f.write(f"📅 Updated: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}\n\n")
        for cat, title in [("alpha","A–Z"),("hiragana","あ〜（ひらがな/漢字）"),("katakana","ア〜（カタカナ）"),("other","その他")]:
            if groups[cat]:
                f.write(f"--- {title} ---\n")
                for it in groups[cat]:
                    f.write(f"{it['raw']:<20} | {it['date']}\n")
                f.write("\n")

def push_to_github():
    repo = Repo(REPO_PATH)
    repo.git.add(".")
    repo.index.commit(f"update: {datetime.datetime.now()}")
    origin = repo.remote(name="origin")
    origin.push()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    text = message.content.strip()
    if not text:
        return
    date = message.created_at.strftime("%Y/%m/%d")
    key = normalize(text)
    data[key] = {"raw": text, "date": date}
    write_txt()
    push_to_github()
    await bot.process_commands(message)

bot.run(TOKEN)

