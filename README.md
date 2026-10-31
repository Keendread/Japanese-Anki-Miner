# Japanese-Anki-Miner

## How to run
Run start.bat

## Anki sync
On the first successful startup with AnkiConnect available, the app scans every
deck in the open Anki profile, including hierarchical decks and their subdecks,
and records notes with an `Expression` field in `data/mined_words.db`. Later
startups skip this sync. If the initial sync cannot complete, it is retried on
the next startup. Use **Reconstruct Mined Words Database** in Settings to
replace the local mined-word list with a fresh scan of all decks. Existing
entries in `data/mined.db` are migrated into the new database automatically.
