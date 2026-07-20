import logging

from core.signals import signals


def show_loading_toast(main_thread_queue, ocr_event, parser_event, dict_event,
                        on_all_ready=None):
    logging.info("[Notifier] Emitting show_loading")
    signals.show_loading.emit(ocr_event, parser_event, dict_event, on_all_ready)


def show_ready_toast(main_thread_queue=None):
    logging.info("[Notifier] Emitting show_ready")
    signals.show_ready.emit()


def show_card_toast(payload, settings, main_thread_queue=None,
                     on_confirm=None, on_discard=None):
    logging.info(f"[Notifier] Emitting show_card for {payload.surface}")
    signals.show_card.emit(payload, settings, on_confirm, on_discard)


def show_duplicate_toast(surface: str, reading: str, main_thread_queue=None):
    logging.info(f"[Notifier] Emitting show_duplicate: {surface} ({reading})")
    signals.show_duplicate.emit(surface, reading)


def show_success_toast(surface: str, main_thread_queue=None):
    logging.info(f"[Notifier] Emitting show_success for {surface}")
    signals.show_success.emit(surface)