import os
import sys
import numpy as np

_session = None
_tokenizer = None


def _get_model_dir() -> str:
    base = os.environ.get("RESOURCEPATH", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "models", "minilm")


def _load() -> None:
    global _session, _tokenizer
    if _session is not None:
        return

    model_dir = _get_model_dir()
    onnx_path = os.path.join(model_dir, "model_quantized.onnx")
    tok_path   = os.path.join(model_dir, "tokenizer.json")

    if not os.path.exists(onnx_path):
        raise FileNotFoundError(
            f"ONNX model not found at {onnx_path}. "
            "Run scripts/download_model.py to fetch all-MiniLM-L6-v2."
        )

    import onnxruntime as ort
    from tokenizers import Tokenizer

    _tokenizer = Tokenizer.from_file(tok_path)
    _tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=128)
    _tokenizer.enable_truncation(max_length=128)

    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 1
    opts.intra_op_num_threads = 2
    _session = ort.InferenceSession(onnx_path, sess_options=opts)


def embed(text: str) -> np.ndarray:
    _load()
    enc = _tokenizer.encode(text)
    input_ids      = np.array([enc.ids],       dtype=np.int64)
    attention_mask = np.array([enc.attention_mask], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)

    outputs = _session.run(
        None,
        {
            "input_ids":      input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )
    # Mean pool last hidden state
    hidden = outputs[0]  # (1, seq_len, 384)
    mask   = attention_mask[0].astype(np.float32)
    vec    = (hidden[0] * mask[:, None]).sum(0) / mask.sum()
    norm   = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec.astype(np.float32)
