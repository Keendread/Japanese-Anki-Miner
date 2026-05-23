# Installing & Running JAM

This guide is for **users who have downloaded the JAM executable**.

If you're a **developer** looking to build from source, see [BUILD_GUIDE.md](BUILD_GUIDE.md).

## System Requirements

- **Windows 10** or later (64-bit)
- **Anki Desktop** installed
- **AnkiConnect add-on** installed
- **VOICEVOX** installed (for audio)
- ~1-2 GB free disk space

## Installation

### Step 1: Download JAM

1. Download `JAM-v*.zip` from releases
2. Extract to a folder (e.g., `C:\Users\YourName\JAM`)

### Step 2: Install Dependencies

#### Anki + AnkiConnect

1. **Install [Anki Desktop](https://apps.ankiweb.net/)**
2. **Install AnkiConnect add-on:**
   - Open Anki
   - Go to Tools → Add-ons → Get Add-ons
   - Enter code: `2055492159`
   - Restart Anki

#### VOICEVOX (for audio)

1. Download from [voicevox.hiroshiba.jp](https://voicevox.hiroshiba.jp)
2. Install and run (keep it running while using JAM)

### Step 3: Prepare Dictionary

1. Download [JMdict_e.xml](https://www.edrdg.org/jmdict/edict_doc.html)
2. Place in `JAM` folder: `data/JMdict_e.xml`

On first launch, JAM will build the dictionary database (takes 5-10 minutes).

## Running JAM

### Launch the App

1. **Open** `JAM.exe` (or use desktop shortcut)
2. **System tray icon** appears (green square with "JAM")
3. App runs in background

### Using JAM

**To capture and create a card:**

1. Press the hotkey (default: `Alt + S`)
2. Drag to select text on screen
3. JAM will:
   - Extract text via OCR
   - Search for images
   - Open image picker
   - Create Anki card

**To access menu:**
- Right-click the tray icon
- Choose: Settings, View Logs, or Exit

## Configuration

Settings are stored in `core/settings.json`.

**Key settings:**

| Setting | Default | Description |
|---------|---------|-------------|
| `capture_combo` | `["alt", "s"]` | Hotkey for capture |
| `anki_deck` | `"Test Deck"` | Target Anki deck |
| `anki_media_path` | Auto-detected | Anki media folder |
| `capture_mode` | `"bbox"` | Capture mode (bbox, window, fullscreen) |

To change hotkey:
1. Stop JAM
2. Edit `src/core/settings.json`
3. Change `"capture_combo"` (e.g., `["ctrl", "alt", "j"]`)
4. Restart JAM

## Troubleshooting

### JAM won't start

**Issue:** Executable opens but nothing happens

**Solution:**
1. Open PowerShell in JAM folder
2. Run: `JAM.exe` (not double-click)
3. Look for error messages
4. Check `BUILD_GUIDE.md` → Troubleshooting

### Hotkey doesn't work

**Issue:** `Alt+S` doesn't trigger capture

**Solution:**
- Try a different hotkey (some apps capture global hotkeys)
- Edit `src/core/settings.json`
- Restart JAM

### No images found

**Issue:** Image picker shows 0 results

**Solution:**
- Check internet connection
- Try different search terms (app uses Japanese → English fallback)
- Check Bing not blocked in your region

### Cards not created

**Issue:** Hotkey works, but no card appears in Anki

**Solution:**
1. Ensure **Anki is open** and AnkiConnect is running
2. In PowerShell (JAM folder), run: `JAM.exe` to see errors
3. Check deck name matches in settings
4. Verify AnkiConnect add-on version (2.1.x or 2.0.x)

### First launch takes forever

**Issue:** App seems frozen on startup

**Solution:**
- **This is normal!** First launch builds the dictionary database (5-10 minutes)
- Don't close the app
- Check `JAM.log` for progress (if available)

### "AnkiConnect not reachable" warning

**Issue:** Warning appears on startup

**Solution:**
- Open Anki and keep it running
- Restart JAM

## Uninstalling

1. **Delete the JAM folder**
2. (Optional) **Remove desktop shortcut**
3. Done! No registry entries or system-wide changes.

## Getting Help

If you encounter issues:

1. **Check logs:** Right-click tray → View Logs
2. **Check GitHub Issues:** [Group-7-Japanese-Anki-Miner/issues](https://github.com/Keendread/Group-7-Japanese-Anki-Miner/issues)
3. **Report a bug:** Include error message and screenshot

## Advanced: Settings File

Located at: `src/core/settings.json`

Example configuration:

```json
{
    "anki_deck": "Japanese",
    "anki_media_path": "C:/Users/YourName/AppData/Roaming/Anki2/User 1/collection.media",
    "capture_combo": ["alt", "s"],
    "capture_mode": "bbox",
    "voicevox_port": 50021
}
```

**Options:**
- `capture_combo`: Array of keys. Valid: `"ctrl"`, `"alt"`, `"shift"`, or lowercase letters
- `capture_mode`: `"bbox"` (drag to select), `"window"` (click window), `"fullscreen"` (entire screen)
- `voicevox_port`: Port VOICEVOX listens on (default: 50021)

## Performance Tips

- **Keep Anki open** while using JAM (faster card creation)
- **Pre-cache OCR model:** First time takes longer (~30s), subsequent captures are fast
- **Minimize other applications** for smoother screen capture

---

**Enjoy mining Japanese with JAM!** 🎌
