"""
The entry point for the bot. Pulls in environment variables and
runs the client.
"""

from client import WordBearerClient
from dotenv import load_dotenv
import os
import logging
from loguru import logger

JOB_DIR = "MESSAGE_JOB_DIR"
FINISHED_JOB_DIR = "FINISHED_MESSAGE_JOB_DIR"
LEAGUE_DIR = "LEAGUE_DIR"
BOT_TOKEN = "BOT_TOKEN"
LOG_FILE = "LOG_FILE"


class LoguruHandler(logging.Handler):
    """
    Adapter from stdlib logging to loguru so
    that logging is unified
    """

    def emit(self, record: logging.LogRecord):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def safe_env(key: str) -> str:
    """Retrieves a required environment variable.

    Args:
        key (str): The key to retrieve

    Raises:
        RuntimeError: If the key is not present

    Returns:
        str: The retrieved value
    """
    value = os.getenv(key)
    if value is None:
        raise RuntimeError(f"Required configuration {key} is not set")
    return value


def main():
    """
    Retrieves configuration from environment and
    runs the bot.
    """
    load_dotenv()
    job_dir = safe_env(JOB_DIR)
    finished_job_dir = safe_env(FINISHED_JOB_DIR)
    league_dir = safe_env(LEAGUE_DIR)
    bot_token = safe_env(BOT_TOKEN)
    log_file = safe_env(LOG_FILE)
    logger.add(log_file)
    discord_client = WordBearerClient(job_dir, finished_job_dir, league_dir)
    discord_client.run(bot_token, log_handler=LoguruHandler())


if __name__ == "__main__":
    main()
