# Group-7-Japanese-Anki-Miner
## TODO (can be done in parallel, do some testing as well)  
### Core Functionalities:
- capture.py
> Do some tests on text/images/videos and see if it correctly frames an area that OCR can use to detect text
- ocr.py
> For testing, use ICDAR 2019, Manga109 samples. Custom-made testing set will be made later.
- parser.py
> For testing, use UD Japanese GSD
> Fills in applicable information in the word.py class to organize relevant information about a term
> Fills in applicable parts of the card.py class for later card creation 
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
