# Group-7-Japanese-Anki-Miner
## TODO (can be done in parallel, do some testing as well)  
### Core Functionalities:
- capture.py
> Will experiment on implementing a text detector which will run before the OCR so that we can subdivide
> large regions into smaller regions, with the regions perfectly cropped onto the text (basically an
> automatic image preprocess). Then merging these subdivisions into one image and then running OCR on it,
> or maybe just run OCR individually on each subdivisions, and then extracting the texts and placing them
> all into one string. This is how Google Lens works (Image -> Text Detector -> Subdivide -> Extract text)
> This should improve MangaOCR accuracy.
- ocr.py
> For testing, use ICDAR 2019, Manga109 samples. Custom-made testing set will be made later.
> **Get performance metric on the datasets.**
- parser.py
> For testing, use UD Japanese GSD
> Fills in applicable information in the word.py class to organize relevant information about a term
> Fills in applicable parts of the card.py class for later card creation
> **Get performance metric on the datasets.**
- dictionary.py
> Use JMDict, but can add fallback dictionaries if you want
> Fills in the translation/meaning part of the word.py and card.py classes
- audio.py
> Uses VOICEVOX for sentence audio, and audio databases for words
- anki.py
> Research on AnkiConnectAPI and how to integrate with Anki
> Uses information from the word.py and card.py classes to create a card

### UI:  
- region_select.py
> Region selection when on Manual Mode
> Automatic Region Selection when on Automatic Mode
> Possible implementations:
> - use OCR and perform OCR multiple times until desired word/sentence is detected
> - Connected Component Analysis
> - CRAFT Text Detector
- tray.py
> Menu when you rightclick the app icon on the system tray (The one on the bottom right of the windows screen)

### Testing:
- test_anki.py
> Test if it generates Anki cards correctly.
- test_dictionary.py
> Test if it correctly returns the right fields, correctly parse XML, does it handle unknown words gracefully?
- test_ocr.py
> ICDAR 2019, Manga109, custom-made set. Generate the relevant metrics (found in proposal paper)
- test_parser.py
> UD Japanese GSD, custom-made set. Generate relevant metrics (found in proposal paper)

### Resources:
- System Tray Icon for the Application

### User Personalization (FR4)
- Personal Frequency Tracker
> Tracks of how many words a user mines per day/week/month
- Duplication Detection Feature

### User-Feedback Loop (FR5)
- Thumbs up/down system for created cards
