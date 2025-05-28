import discord
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

class DiscordClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.ready_event = None

    async def on_ready(self):
        print(f"✅ Discord 봇 로그인됨: {self.user}")
        self.ready_event = True

    async def send_til_to_thread(self, content: str, username: str):
        await self.wait_until_ready()
        channel = self.get_channel(DISCORD_CHANNEL_ID)

        if not channel:
            print("❌ 채널을 찾을 수 없습니다.")
            return

        today = datetime.now().strftime("%Y-%m-%d")

        # 스레드 찾기
        threads = channel.threads 
        thread = next((t for t in threads if t.name == today), None)

        if not thread:
            thread = await channel.create_thread(
                name=today,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=1440  # 24시간 후 자동 보관
            )

        # 본문 길이 제한
        if len(content) > 1800:
            content = content[:1800] + "\n...(생략됨)"

        message = f"👤 생성자: {username}\n\n 📘 TIL 본문:\n\n{content} \n"
        await thread.send(message)