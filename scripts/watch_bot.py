import logging
from logging.handlers import RotatingFileHandler
import subprocess
import sys
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent / "watch_bot.log"
MAX_BYTES = 524_288  # 512KB (reduced from 2MB for better performance on old Android devices)
BACKUP_COUNT = 2  # Reduced from 5 to minimize storage usage


def configure_logger():
    logger = logging.getLogger("watch_bot")
    # Reduce logging verbosity for better performance on old Android devices
    logger.setLevel(logging.WARNING)
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
            result = subprocess.run([sys.executable, "-m", "bot.main"], check=False)
            if result.returncode == 0:
                logger.info("bot.main exited with code 0, relaunching")
            else:
                logger.error("bot.main exited with code %s, relaunching", result.returncode)
        except Exception:
            logger.exception("bot main execution failed, relaunching")
        
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
