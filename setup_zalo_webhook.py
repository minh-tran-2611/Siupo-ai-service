"""Quick script to register Zalo webhook."""
import asyncio
import httpx

ZALO_BOT_TOKEN = "197912927516328658:bexRmZAKgdEEUYdejYeLCVdFRearZKWvVpcMjhXmLfOvPomNaqsfqwTidpzrvFrw"
WEBHOOK_URL = "https://certificatory-intensely-pricilla.ngrok-free.dev/api/webhook/zalo"
SECRET_TOKEN = "siupo_zalo_webhook_2026"

async def main():
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Set webhook
        resp = await client.post(
            f"https://bot-api.zaloplatforms.com/bot{ZALO_BOT_TOKEN}/setWebhook",
            json={"url": WEBHOOK_URL, "secret_token": SECRET_TOKEN},
        )
        print("setWebhook:", resp.json())

        # Verify
        resp2 = await client.post(
            f"https://bot-api.zaloplatforms.com/bot{ZALO_BOT_TOKEN}/getWebhookInfo",
        )
        print("getWebhookInfo:", resp2.json())

asyncio.run(main())
