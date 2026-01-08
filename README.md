# Metafootage – AI-Powered Metadata for DaVinci Resolve

A lightweight **DaVinci Resolve scripting plugin** that uses Google’s Gemini Vision API or OpenAI to analyze video clips and automatically generate rich metadata.

## User Interface

![Metafootage UI showing provider selection, model choice, and proxy settings](media/metafootage-ui.png)

---
## Automatic Metadata Generation

![Metafootage BRAW proxy workflow demo](media/metafootage-demo-2.gif)

---

## What it does

Select clips in the Media Pool → run Metafootage → it:
- extracts a few representative frames per clip
- asks your chosen AI model to describe what’s happening (subject, action, lighting, camera movement, mood, setting)
- writes the results back into Resolve’s metadata fields
- merges with existing notes/keywords instead of nuking them
---

## Key capabilities

### Cinematic analysis
Describes more than “a person in a room” — it’s aimed at editorial usefulness: action, framing, motion, mood, environment.

### Smart metadata merging
Keeps your existing tags/notes and appends new metadata instead of overwriting.

### Model selection
Use a fast/cheap model for bulk bins, or a higher-quality model for hero moments.

### RAW-friendly via proxies
Works cleanly with RAW formats by analyzing proxy media when FFmpeg can’t decode the RAW source. 

### Privacy-conscious
Metafootage doesn’t store your frames beyond what it needs to send the request. (Your AI provider’s retention/logging policies still apply.)

---

## Requirements

- DaVinci Resolve (Studio or Free)
- Python (Resolve scripting)
- FFmpeg (frame extraction)
- A Google Gemini API key **or** an OpenAI API key

---

## What’s Included

This package is intentionally minimal.

* **`Metafootage.py`**
  The DaVinci Resolve script. This is the only file Resolve needs.

* **`README.md`**
  Installation and usage instructions.

* **`LICENSE`**
  MIT License.

---

## Requirements

* **DaVinci Resolve** (Studio or Free)
* **Python 3.6+** (used by Resolve scripting)
* **FFmpeg** (used to extract frames from clips)
* **Google Gemini API key or OPen**

---

## Installing FFmpeg

### Windows

```bash
winget install ffmpeg
```

### macOS

```bash
brew install ffmpeg
```

### Linux

Install via your system package manager (for example):

```bash
apt install ffmpeg
```

---

## Installation (DaVinci Resolve)

1. Copy **`Metafootage.py`** to your Resolve Scripts folder:

   **Windows**

   ```
   %APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit\
   ```

   **macOS**

   ```
   ~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit/
   ```

   **Linux**

   ```
   /opt/resolve/Fusion/Scripts/Edit/
   ```

2. Restart **DaVinci Resolve**.

3. Select one or more clips in the **Media Pool**.

4. Run the script from:
   **Workspace → Scripts → Metafootage**

5. On first run, you will need to to enter your **Gemini or Open API key**.
   The key is stored locally on your machine.

---

## Contributing

If you find this helpful and it saved you time, contributions are welcome but not expected. 
---

## License

Released under the **MIT License**.
See the `LICENSE` file for details.

---

## Author

Created by **Wayne Degan**

