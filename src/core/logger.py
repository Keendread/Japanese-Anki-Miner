"""
logger.py — centralised logging setup and named log helpers for JAM.

Usage:
    from logger import setup_logging, log

    setup_logging(app_dir, log_file)   # call once at startup, before imports
    log.startup("message")             # INFO  with [Startup] tag
    log.settings("message")            # INFO  with [Settings] tag
    log.task("name", "message")        # DEBUG with [Main] tag
    log.pump_error("component", e)     # ERROR with [Pump] tag
    log.shutdown("message")            # INFO  with [Shutdown] tag
    log.warning("message")             # plain WARNING
    log.error("message", exc=e)        # plain ERROR (exc_info if exc given)
    log.exception("message")           # ERROR + full traceback
"""

import logging
import os
from logging.handlers import RotatingFileHandler


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup_logging(app_dir: str, log_file: str) -> None:
    """
    Configures the root logger with a rotating file handler.
    Call once at the very top of main.py, before any other imports.

    Args:
        app_dir:  Root directory of the app (used to ensure it exists).
        log_file: Full path to the .log file.
    """
    os.makedirs(app_dir, exist_ok=True)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=5_242_880,   # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    logging.basicConfig(level=logging.INFO, handlers=[handler])

    # Suppress noisy third-party loggers
    logging.getLogger("manga_ocr").setLevel(logging.ERROR)


# ── Helpers ───────────────────────────────────────────────────────────────────

class _Log:
    """Thin wrapper that adds consistent bracketed tags to log messages."""

    # ── Startup / lifecycle ───────────────────────────────────────────────────

    def startup_banner(self) -> None:
        logging.info("=" * 50)
        logging.info("JAM - Japanese Anki Miner Startup")
        logging.info("=" * 50)

    def startup(self, message: str) -> None:
        logging.info(f"[Startup] {message}")

    def startup_warning(self, message: str) -> None:
        logging.warning(f"[Startup] {message}")

    # ── Settings ──────────────────────────────────────────────────────────────

    def settings(self, message: str) -> None:
        logging.info(f"[Settings] {message}")

    def settings_error(self, message: str, exc: Exception) -> None:
        logging.error(f"[Settings] {message}", exc_info=exc)

    # ── Background tasks ──────────────────────────────────────────────────────

    def task_started(self, task: str) -> None:
        logging.info(f"[Task] {task} started")

    def task_done(self, task: str) -> None:
        logging.info(f"[Task] {task} complete")

    def task_warning(self, task: str, message: str) -> None:
        logging.warning(f"[Task:{task}] {message}")

    # ── Main loop ─────────────────────────────────────────────────────────────

    def loop_started(self) -> None:
        logging.info("[Main] Event loop started")

    def loop_task(self, task_name: str) -> None:
        logging.debug(f"[Main] Executing task: {task_name}")

    def loop_task_done(self, task_name: str) -> None:
        logging.debug(f"[Main] Task completed: {task_name}")

    def loop_interrupted(self) -> None:
        logging.info("[Main] KeyboardInterrupt received")

    def loop_error(self, exc: Exception) -> None:
        logging.exception(f"[Main] Loop error: {exc}")

    # ── Pump errors ───────────────────────────────────────────────────────────

    def pump_error(self, component: str, exc: Exception) -> None:
        logging.error(f"[Pump] Error pumping {component}: {exc}")

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def shutdown(self, message: str) -> None:
        logging.info(f"[Shutdown] {message}")

    def shutdown_done(self) -> None:
        logging.info("[Shutdown] JAM shutdown complete.")

    # ── Generic fallbacks ─────────────────────────────────────────────────────

    def warning(self, message: str) -> None:
        logging.warning(message)

    def error(self, message: str, exc: Exception = None) -> None:
        logging.error(message, exc_info=exc)

    def exception(self, message: str) -> None:
        logging.exception(message)


# Singleton — import and use directly:  log.startup("...")
log = _Log()