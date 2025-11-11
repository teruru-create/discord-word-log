import os
import discord
from discord.ext import commands, tasks
import subprocess
import datetime

TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    print("❌ エラー: DISCORD_TOKEN 環境変数が設定されていません")
    print("✅ 修正方法:")
    print("   1. Discord Developer Portal から有効なボットトークンを取得")
    print("   2. 以下のコマンドでボットを実行:")
    print("   $env:DISCORD_TOKEN='ここにトークンを貼り付け'; python bot.py")
    exit(1)

REPO_PATH = r"C:\Projects\discord-word-log"  # GitHub リポジトリのローカルパス
CHANNEL_ID = 1426221097346400418  # メッセージを取得するチャンネルID
OUTPUT_FILE = os.path.join(REPO_PATH, "output.txt")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    fetch_and_save.start()  # タスク開始

# 定期的に最新メッセージを取得して保存
@tasks.loop(seconds=60)
async def fetch_and_save():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found")
        return

    lines = {}
    async for msg in channel.history(limit=100, oldest_first=True):
        # 最新日付だけ保持
        key = msg.content.strip()
        if key:
            lines[key] = msg.created_at.strftime("%Y/%m/%d")

    # ソート（アルファベット・ひらがな・カタカナ順）
    sorted_lines = sorted(
        lines.items(),
        key=lambda x: (x[0].encode("utf-8"))  # 簡易ソート
    )

    # TXT 書き出し
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=== LINES (unique, sorted) ===\n")
        for text, date in sorted_lines:
            f.write(f"{text} {date}\n")

    # GitHub に push
    try:
        subprocess.run(["git", "add", "output.txt"], cwd=REPO_PATH, check=True)
        subprocess.run(["git", "commit", "-m", "Update output.txt"], cwd=REPO_PATH, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_PATH, check=True)
        print("✅ GitHub updated successfully")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  GitHub push failed: {e}")
    except Exception as e:
        print(f"⚠️  Git operation failed: {e}")

try:
    bot.run(TOKEN)
except discord.errors.LoginFailure:
    print("❌ エラー: Discord トークンが無効です")
    print("✅ 修正方法:")
    print("   1. Discord Developer Portal (https://discord.com/developers/applications) にアクセス")
    print("   2. ボットアプリケーションを選択")
    print("   3. 左側の 'TOKEN' をクリック")
    print("   4. 'Copy' ボタンをクリックして新しいトークンをコピー")
    print("   5. 以下のコマンドで実行:")
    print("   $env:DISCORD_TOKEN='新しいトークン'; python bot.py")
    exit(1)

