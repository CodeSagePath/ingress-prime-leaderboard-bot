import logging
from logging.handlers import RotatingFileHandler
import subprocess
import sys

LOG_FILE = "log.txt"
MAX_BYTES = 2_097_152  # 2MB
BACKUP_COUNT = 5


def configure_logger():
    logger = logging.getLogger("watch_bot")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def run_bot(logger):
    import time
    while True:
        try:
            result = subprocess.run([sys.executable, "bot.py"], check=False)
            if result.returncode == 0:
                logger.info("bot.py exited with code 0, relaunching")
            else:
                logger.error("bot.py exited with code %s, relaunching", result.returncode)
        except Exception:
            logger.exception("bot.py execution failed, relaunching")
        
        # Wait 2 seconds before restarting
        time.sleep(2)


def main():
    logger = configure_logger()
    try:
        run_bot(logger)
    except KeyboardInterrupt:
        logger.info("watch_bot interrupted")


if __name__ == "__main__":
    main()
