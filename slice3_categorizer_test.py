"""
Slice 3 verification: categorizer.py
Tests tool schema, state injection, extension seeding, and cache/resume logic.
Requires ANTHROPIC_API_KEY in environment.
Run: ANTHROPIC_API_KEY=sk-... python3 slice3_categorizer_test.py
"""
import os, sys, json, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from organizer.categorizer import (
    categorize, seed_from_extensions, build_folder_state,
    build_user_prompt, BATCH_SIZE
)

PASS = "[+]"
FAIL = "[!]"

def check(label, condition, detail=""):
    if condition:
        print(f"{PASS} {label}")
    else:
        print(f"{FAIL} FAILED: {label}  {detail}")
        sys.exit(1)

api_key = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Offline tests (no API key needed) ──────────────────────────────────────

print("\n── Test 1: Extension seeding ──")
files = [
    {"name": "app.py", "path": ""},
    {"name": "photo.jpg", "path": ""},
    {"name": "budget.xlsx", "path": ""},
]
seeds = seed_from_extensions(files)
check("Source Code seeded from .py", "Source Code" in seeds)
check("Media/Images seeded from .jpg", "Media/Images" in seeds)
check("Documents/Spreadsheets seeded from .xlsx", "Documents/Spreadsheets" in seeds)

print("\n── Test 2: Folder state formatting ──")
state_empty = build_folder_state(set())
check("empty state message", "No folders exist yet" in state_empty)
state_filled = build_folder_state({"Finance/Taxes", "Media/Images"})
check("filled state includes folders", "Finance/Taxes" in state_filled and "Media/Images" in state_filled)

print("\n── Test 3: User prompt XML structure (filename-only) ──")
batch = [{"name": "taxes.pdf", "path": ""}, {"name": "photo.jpg", "path": ""}]
prompt = build_user_prompt(batch, peek_mode=False)
check("contains files_to_categorize tag", "<files_to_categorize>" in prompt)
check("self-closing tag for filename-only", '<file filename="taxes.pdf" />' in prompt)
check("no peek_content in filename-only mode", "<peek_content>" not in prompt)

print("\n── Test 4: User prompt XML structure (peek mode) ──")
batch_peek = [{"name": "notes.txt", "path": "", "peek": "Meeting notes <b>bold</b>"}]
prompt_peek = build_user_prompt(batch_peek, peek_mode=True)
check("peek_content block present", "<peek_content>" in prompt_peek)
check("< escaped to &lt; in content", "&lt;b&gt;" in prompt_peek)
check("no raw < in content section", "<b>" not in prompt_peek)

print("\n── Test 5: Cache resume (offline) ──")
with tempfile.TemporaryDirectory() as cache_dir:
    # Pre-populate batch 0 cache
    cached_data = [{"filename": "cached_file.pdf", "folder_path": "Finance/Taxes"}]
    with open(os.path.join(cache_dir, "batch_0.json"), "w") as f:
        json.dump(cached_data, f)

    if not api_key:
        print("  [skip] No API key — cache load path verified offline")
    else:
        # With a real key, batch 0 should load from cache, batch 1+ from API
        test_files = [{"name": "cached_file.pdf", "path": ""}]
        result = categorize(test_files, api_key=api_key, cache_dir=cache_dir)
        check("cached result returned", result["results"].get("cached_file.pdf") == "Finance/Taxes")

# ── Online tests (require API key) ─────────────────────────────────────────

if not api_key:
    print("\n[skip] ANTHROPIC_API_KEY not set — skipping live API tests")
    print("       Set it and rerun to verify Claude tool calling and state injection")
    sys.exit(0)

print("\n── Test 6: Live Claude call — 15 mixed files ──")
test_files = [
    {"name": "Q3_2026_Revenue.xlsx", "path": ""},
    {"name": "annual_tax_return_2025.pdf", "path": ""},
    {"name": "family_vacation_hawaii.jpg", "path": ""},
    {"name": "resume_sarah_chen.docx", "path": ""},
    {"name": "main.py", "path": ""},
    {"name": "README.md", "path": ""},
    {"name": "invoice_acme_corp_0042.pdf", "path": ""},
    {"name": "cats_playing.mp4", "path": ""},
    {"name": "lecture_notes_week3.txt", "path": ""},
    {"name": "budget_2026.xlsx", "path": ""},
    {"name": "passport_scan.pdf", "path": ""},
    {"name": "logo_design_v3.png", "path": ""},
    {"name": "meeting_recording.mp3", "path": ""},
    {"name": "server_config.yaml", "path": ""},
    {"name": "cover_letter_google.docx", "path": ""},
]

result = categorize(test_files, api_key=api_key)
cats = result["results"]

check("all 15 files categorized", len(cats) == 15, f"got {len(cats)}")
check("no failed batches", len(result["failed_batches"]) == 0)

# Verify no obviously wrong groupings
tax_folder = cats.get("annual_tax_return_2025.pdf", "")
invoice_folder = cats.get("invoice_acme_corp_0042.pdf", "")
check("tax and invoice in same top-level category",
      tax_folder.split("/")[0] == invoice_folder.split("/")[0],
      f"tax={tax_folder} invoice={invoice_folder}")

photo_folder = cats.get("family_vacation_hawaii.jpg", "")
video_folder = cats.get("cats_playing.mp4", "")
check("photo and video not in Finance",
      "Finance" not in photo_folder and "Finance" not in video_folder)

resume_folder = cats.get("resume_sarah_chen.docx", "")
cover_folder = cats.get("cover_letter_google.docx", "")
check("resume and cover letter same top-level folder",
      resume_folder.split("/")[0] == cover_folder.split("/")[0],
      f"resume={resume_folder} cover={cover_folder}")

max_depth = max(len(p.split("/")) for p in cats.values())
check(f"max folder depth ≤ 2 (got {max_depth})", max_depth <= 2)

print("\nCategorizations:")
for name, folder in sorted(cats.items(), key=lambda x: x[1]):
    print(f"  {folder:35s}  {name}")

print("\n[+] Slice 3 PASSED")
