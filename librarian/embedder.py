import os
import sys
import numpy as np
from tokenizers import Tokenizer
import onnxruntime as ort

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In production (py2app), RESOURCEPATH points to Contents/Resources/
RESOURCE_BASE = os.environ.get("RESOURCEPATH", os.path.join(BASE_DIR, "models", "minilm"))

_tokenizer = None
_session = None


def _load():
    global _tokenizer, _session
    if _tokenizer is None:
        tok_path = os.path.join(RESOURCE_BASE, "tokenizer.json")
        _tokenizer = Tokenizer.from_file(tok_path)
        _tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=128)
        _tokenizer.enable_truncation(max_length=128)

    if _session is None:
        model_path = os.path.join(RESOURCE_BASE, "model.onnx")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 2
        _session = ort.InferenceSession(model_path, sess_options=opts)


def mean_pool(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    mask = attention_mask[..., np.newaxis].astype(np.float32)
    summed = (token_embeddings * mask).sum(axis=1)
    counts = mask.sum(axis=1).clip(min=1e-9)
    return summed / counts


def embed(texts: list[str]) -> np.ndarray:
    """Returns shape (N, 384) float32 normalized embeddings."""
    _load()
    encoded = _tokenizer.encode_batch(texts)
    input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)

    outputs = _session.run(None, {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": token_type_ids,
    })
    # outputs[0] is token embeddings shape (N, seq_len, 384)
    pooled = mean_pool(outputs[0], attention_mask)
    norms = np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
    return (pooled / norms).astype(np.float32)


def embed_one(text: str) -> np.ndarray:
    return embed([text])[0]
