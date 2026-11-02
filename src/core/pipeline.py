import asyncio
import dataclasses
import logging
import queue
import threading
from concurrent.futures import Future
from typing import List, Optional, Tuple

from PIL import Image

from core import ocr
from core import parser
from core import dictionary
from core import anki
from core import notifier
from core import audio
from core import image as image_module
from core.mined_words_db import normalize_word_identity
from core.detector import TextRegion
from src.models.word import Word
from src.models.card import Card
from src.models.audio import AudioFile
from src.ui.word_selector import WordEntry, show_word_selector


# ── Model readiness ───────────────────────────────────────────────────────────

def wait_for_ready(timeout: float = 30.0) -> bool:
    ocr_ready    = ocr._model_ready.is_set()
    parser_ready = parser._parser_ready.is_set()

    if not ocr_ready or not parser_ready:
        ocr_status    = "✓" if ocr_ready    else "..."
        parser_status = "✓" if parser_ready else "..."
        print(f"[JAM] Models still loading "
              f"(OCR: {ocr_status}  Parser: {parser_status}) — waiting...")

    if not ocr._model_ready.wait(timeout=timeout):
        print("[JAM] Timed out waiting for OCR model.")
        return False

    if not parser._parser_ready.wait(timeout=timeout):
        print("[JAM] Timed out waiting for parser.")
        return False

    return True


# ── OCR helpers ───────────────────────────────────────────────────────────────

def ocr_all_regions(
    full_image: Image.Image,
    regions:    Optional[List[TextRegion]] = None,
    translate:  bool = True,
) -> List[Tuple[TextRegion, str]]:
    print("[OCR] Running Lens block detection...")
    logging.info("[OCR] Running Lens block detection...")

    blocks = ocr.extract_blocks(full_image)
    blocks = [b for b in blocks if b.text.strip()]

    if translate and blocks:
        print(f"[OCR] Translating {len(blocks)} block(s)...")
        ocr.translate_blocks(full_image, blocks, target_lang="en")

    results: List[Tuple[TextRegion, str]] = [(block, block.text) for block in blocks]

    for region, text in results:
        print(f"[OCR] Block result: '{text}' -> '{region.translation}'")

    print(f"[OCR] {len(results)} non-empty result(s)")
    return results


# ── Word building ─────────────────────────────────────────────────────────────

def _finalize_sentence_furigana(word: Word) -> None:
    best = word.best_sentence()
    if not best:
        return
    if best.strip() == (word.full_sentence or "").strip():
        return   # OCR was a real sentence — furigana already correct
    morphemes = parser.tokenize(best)
    word.sentence_furigana = parser.build_sentence_furigana(morphemes)


def build_word_entries(
    ocr_results: List[Tuple[TextRegion, str]],
    full_image:  Image.Image,
) -> List[WordEntry]:
    print(f"[Pipeline] Building word entries from {len(ocr_results)} OCR result(s)")
    logging.info(f"[Pipeline] Building word entries from {len(ocr_results)} OCR result(s)")

    entries: List[WordEntry] = []
    seen: set[Tuple[str, str]] = set()

    for block_index, (region, text) in enumerate(ocr_results):
        morphemes = parser.tokenize(text)

        if not morphemes:
            # Fall back to single-target parse if tokenizer returns nothing
            parse_result = parser.parse(text)
            if not parse_result:
                continue
            morpheme_list = [parse_result]
        else:
            morpheme_list = []
            for m in morphemes:
                pos = m.part_of_speech()[0]
                if pos in ("助詞", "助動詞", "補助記号", "空白"):
                    continue   # skip particles, punctuation, whitespace
                morpheme_list.append({
                    "surface":          m.surface(),
                    "dictionary_form":  m.dictionary_form(),
                    "reading":          parser._kata_to_hira(m.reading_form()),
                    "pos":              pos,
                    "sentence":         text,
                    "sentence_furigana": parser.build_sentence_furigana(morphemes),
                })

        for parse_result in morpheme_list:
            dict_form = parse_result.get("dictionary_form", "")
            reading = parse_result.get("reading", "")
            identity = normalize_word_identity(dict_form, reading)
            if not dict_form or identity in seen:
                continue
            seen.add(identity)

            word = Word(
                surface          = parse_result.get("surface", ""),
                dictionary_form  = dict_form,
                reading          = reading,
                pos              = parse_result.get("pos", ""),
                meaning          = None,
                full_sentence    = parse_result.get("sentence", text),
                sentence_furigana= parse_result.get("sentence_furigana", ""),
            )

            word.sentence_translation = region.translation

            word._card_image = full_image

            dict_result = dictionary.lookup(word)
            if dict_result is None:
                word.meaning = "(not in dictionary)"
            else:
                word.update_from_dictionary(dict_result)
            _finalize_sentence_furigana(word)

            is_mined = anki.is_already_mined(
                word.dictionary_form,
                word.reading,
                surface=word.surface,
            )
            entries.append(WordEntry(
                word=word, is_mined=is_mined, selected=not is_mined,
                block_index=block_index, block_text=text,
                block_translation=region.translation,
            ))
            print(f"[Pipeline] Entry: {word.surface} ({word.dictionary_form}), mined={is_mined}, block={block_index}")

    print(f"[Pipeline] {len(entries)} word entries built")
    return entries


# ── Card flow ─────────────────────────────────────────────────────────────────

def run_card_flow(
    card:       Card,
    settings,
    main_queue: queue.Queue,
    blocking:   bool = False,
) -> None:
    logging.info(f"[Flow] Card flow for {card.source_word.surface}")

    audio_future: Future[Optional[AudioFile]] = Future()

    def _run_audio():
        try:
            result = asyncio.run(audio.fetch_audio(card.source_word, settings=settings))
            logging.info("[Flow] Audio fetched" if result else "[Flow] Audio returned None")
            audio_future.set_result(result)
        except Exception as e:
            logging.error(f"[Flow] Audio fetch failed: {e}", exc_info=True)
            audio_future.set_result(None)

    threading.Thread(target=_run_audio, daemon=True).start()

    done_event = threading.Event()

    def on_confirm():
        logging.info(f"[Flow] User confirmed: {card.source_word.surface}")

        image_filename = None
        card_image = getattr(card.source_word, "_card_image", None)
        if card_image is not None:
            try:
                image_filename = image_module.save_captured_image(
                    card_image, settings)
                logging.info(f"[Flow] Image saved: {image_filename}")
            except Exception as e:
                logging.error(f"[Flow] Image save failed: {e}", exc_info=True)
        else:
            logging.warning("[Flow] No card image on word — card will have no image")

        success, message, note_id = anki.add_card(
            card, settings, image_filename=image_filename)

        if success:
            logging.info(f"[Flow] Card added: {message}")
            print(f"[Anki] {message}")
            notifier.show_success_toast(card.source_word.surface, main_queue)
        else:
            logging.error(f"[Flow] Card add failed: {message}")
            print(f"[Anki] Failed: {message}")

        def _apply_audio():
            try:
                af = audio_future.result(timeout=30.0)
            except Exception as e:
                logging.warning(f"[Flow] Audio future timeout: {e}")
                af = None

            recorded_path = card.source_word.sentence_audio
            if af and recorded_path:
                logging.info(f"[Flow] Using recorded sentence audio: {recorded_path}")
                af = dataclasses.replace(af, sentence_audio=recorded_path)

            if af and note_id:
                try:
                    anki.update_card_audio(note_id, af)
                    logging.info("[Flow] Audio applied")
                except Exception as e:
                    logging.error(f"[Flow] Audio apply failed: {e}", exc_info=True)

        threading.Thread(target=_apply_audio, daemon=True).start()
        done_event.set()

    def on_discard():
        logging.info(f"[Flow] User discarded: {card.source_word.surface}")
        print(f"[Flow] Discarded: {card.source_word.surface}")
        done_event.set()

    notifier.show_card_toast(
        card.source_word, settings, main_queue,
        on_confirm=on_confirm, on_discard=on_discard,
    )

    if blocking:
        done_event.wait(timeout=120.0)


# ── Pipeline entry points ─────────────────────────────────────────────────────
def process_multi(
    full_image: Image.Image,
    filepath:   str,
    settings,
    main_queue: queue.Queue,
) -> None:
    print("[Pipeline] Multi: running Lens block OCR...")
    ocr_results = ocr_all_regions(full_image)

    if not ocr_results:
        return

    entries   = build_word_entries(ocr_results, full_image)
    new_count = sum(1 for e in entries if not e.is_mined)
    print(f"[Pipeline] {len(entries)} unique words — {new_count} new.")

    if new_count == 0:
        notifier.show_duplicate_toast("(all words)", "already mined", main_queue)
        return

    def on_confirmed(selected: List[WordEntry]):
        if not selected:
            print("[Pipeline] Nothing selected.")
            return
        print(f"[Pipeline] Mining {len(selected)} word(s)...")
        for entry in selected:
            entry.word.capture_path = filepath
            card = Card.from_word(entry.word, settings)
            if card.is_valid():
                run_card_flow(card, settings, main_queue, blocking=True)

    show_word_selector(entries, main_queue, on_confirmed, settings)