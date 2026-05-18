"""
Downloads the quantized all-MiniLM-L6-v2 ONNX model + tokenizer files
into models/minilm/ for use by the Librarian embedder.

Usage: python scripts/download_model.py
"""
import os
import urllib.request

DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "minilm")
HF_BASE = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main"
ONNX_BASE = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx"

FILES = [
    (f"{ONNX_BASE}/model_quantized.onnx", "model_quantized.onnx"),
    (f"{HF_BASE}/tokenizer.json",          "tokenizer.json"),
    (f"{HF_BASE}/vocab.txt",               "vocab.txt"),
]

os.makedirs(DEST, exist_ok=True)

for url, filename in FILES:
    dst = os.path.join(DEST, filename)
    if os.path.exists(dst):
        print(f"  skip (exists): {filename}")
        continue
    print(f"  downloading: {filename} …", end="", flush=True)
    urllib.request.urlretrieve(url, dst)
    print(f" {os.path.getsize(dst) // 1024}KB")

print(f"\nModel files ready in {DEST}")
