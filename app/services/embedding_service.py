import hashlib
import math
import re


VECTOR_DIM = 384
EMBEDDING_MODEL_NAME = "local-hash-v1"


def embed_text(text: str, vector_dim: int = VECTOR_DIM) -> list[float]:
    tokens = _tokenize(text)
    vector = [0.0] * vector_dim

    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % vector_dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector

    return [value / norm for value in vector]


def embed_texts(texts: list[str], vector_dim: int = VECTOR_DIM) -> list[list[float]]:
    return [embed_text(text, vector_dim=vector_dim) for text in texts]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text.lower())
