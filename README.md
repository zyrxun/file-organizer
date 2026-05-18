# File Organizer + Librarian

A Mac-first desktop app that organises messy folders using AI and lets you search your files in plain English.

---

## What it does

### Organiser
- Pick a folder → AI proposes a categorised folder tree (e.g. `Finance/Taxes`, `Media/Images`)
- Preview every proposed move before anything happens
- Confirm to execute, or undo with one click
- Optional **Peek Mode**: reads up to 500 chars of file content for smarter sorting (opt-in, read-only)
- Filter by **date range** — only sort files modified or created within a specific window

### Librarian
- Indexes your organised folder locally (no cloud)
- Search in plain English: *"quarterly tax spreadsheet"*, *"photo of my cat"*
- Results ranked by semantic similarity — not just filename matching
- Live sync: automatically updates as you add, move, or delete files

---

## Privacy

- **Filename-only mode (default):** only filenames are sent to the Claude API
- **Peek mode (opt-in):** up to 500 characters of text content sent per file — never stored, never written
- All embeddings and search index stored locally in `~/Library/Application Support/FileOrganizer/`
- API key stored in macOS Keychain — never written to disk

---

## Requirements

- macOS 12+
- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com) (~$0.01–0.10 per organise run)

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/zyrxun/file-organizer.git
cd file-organizer

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download the embedding model (~87MB, one-time)
python3 scripts/download_model.py

# 5. Launch
python3 main.py
```

On first launch, the app will prompt you to enter your Anthropic API key. It's stored securely in the macOS Keychain.

---

## Project structure

```
file-organizer/
├── main.py                  # Entry point
├── config.py                # API key + DB path config
├── organizer/
│   ├── scanner.py           # Walks directory, collects file metadata
│   ├── categorizer.py       # Claude API via tool calling + state-of-tree injection
│   ├── content_extractor.py # Read-only text extraction for Peek Mode
│   ├── date_filter.py       # Date range filtering
│   ├── mover.py             # Atomic moves, collision handling, undo
│   └── tree_renderer.py     # Navigation tree renderer
├── librarian/
│   ├── _db.py               # SQLite + sqlite-vec connection helper
│   ├── _embedder.py         # ONNX Runtime embedder (no PyTorch)
│   ├── indexer.py           # Startup diff sync + live watchdog
│   └── searcher.py          # Semantic + fallback LIKE search
├── gui/
│   ├── app.py               # Main window + settings dialog
│   ├── organizer_tab.py     # Organiser UI
│   └── librarian_tab.py     # Librarian UI
├── models/minilm/           # Bundled ONNX model (all-MiniLM-L6-v2)
└── scripts/
    └── download_model.py    # One-time model download
```

---

## Licence

Dual-licensed:
- **Source code:** [GPLv3](LICENSE) — free to use, modify, and distribute with source disclosure
- **Commercial use:** contact for a commercial licence

---

## Roadmap

- [ ] Date filter UI (in progress)
- [ ] Windows support
- [ ] Mac App Store distribution
- [ ] Image categorisation via local CLIP model
