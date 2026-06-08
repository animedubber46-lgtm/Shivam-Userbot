"""
Run this script once to generate a STRING_SESSION for your userbot.
It will print the session string — copy it into your .env file.

Usage:
    python generate_session.py
"""
import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")


async def generate():
    if not API_ID or not API_HASH:
        print("Error: Set API_ID and API_HASH in your .env file first.")
        return

    async with Client(
        name="session_generator",
        api_id=API_ID,
        api_hash=API_HASH,
    ) as app:
        session_string = await app.export_session_string()
        print("\n" + "=" * 60)
        print("Your STRING_SESSION (add this to .env):")
        print("=" * 60)
        print(session_string)
        print("=" * 60 + "\n")
        print("⚠️  Keep this string secret — it gives full access to your account.")


if __name__ == "__main__":
    asyncio.run(generate())
