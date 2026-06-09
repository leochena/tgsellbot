import asyncio
import logging

import uvicorn
from dotenv import load_dotenv

load_dotenv(encoding="utf-8")

from bot.misc import EnvKeys
from bot.web import create_admin_app


async def main() -> None:
    """Run only the local web admin/client app, without Telegram polling."""
    logging.basicConfig(
        level=logging.DEBUG if EnvKeys.DEBUG == "1" else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    app = create_admin_app()
    config = uvicorn.Config(
        app,
        host=EnvKeys.ADMIN_HOST,
        port=EnvKeys.ADMIN_PORT,
        log_level="info" if EnvKeys.DEBUG == "1" else "warning",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
