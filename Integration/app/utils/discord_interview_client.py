from concurrent.futures import thread
from multiprocessing.connection import Client
import discord
from datetime import datetime
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()
DISCORD_CHANNEL = int(os.getenv("DISCORD_CHANNEL"))
TOKEN = os.getenv("DISCORD_TOKEN")
 
class DiscordClientInterview(discord.Client):
    def __init__(self) -> None:
        intents =discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.ready_event = None

    async def on_ready(self):
        #print(f"Discord 봇 로그인 됨")
        self.ready_event = True
    
    async def send_interview_to_channel(self, email: str, summary: str, content: list[dict]) -> None:
        await self.wait_until_ready()
        channel = self.get_channel(DISCORD_CHANNEL)

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

        for i, qa in enumerate(content, start=1):
            question = qa.get("question", "").strip()
            answer = qa.get("answer", "").strip()

            if not question and not answer:
                continue

            message = (
                f"# 📧 이메일: {email}\n\n"
                f"# 🧐 제목: {summary}\n\n"
                f"### Q{i}. {question}\n" 
                f"{answer}\n\n"
            )

            if len(message) > 2000:
                message = message[:1990] + "\n(이하 생략)"

            await thread.send(content=message)
            await asyncio.sleep(1)