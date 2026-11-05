"""Build the policy index: child chunks -> embeddings -> Qdrant (local folder), parents -> JSON for expansion.

CLI (from repo root):  python -m src.rag.index [--model BAAI/bge-small-en-v1.5]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.rag.embedder import get_embedder

COLLECTION = "policy_children"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def make_client(path: str) -> QdrantClient:
    return QdrantClient(":memory:") if path == ":memory:" else QdrantClient(path=path)


def load_chunks(chunks_dir: str) -> tuple[list[dict], dict[str, dict]]:
    children, parents = [], {}
    for f in sorted(Path(chunks_dir).glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["type"] == "child":
                children.append(r)
            else:
                parents[r["chunk_id"]] = r
    return children, parents


def embed_text(c: dict) -> str:
    return f"{c['context']}\n{c['text']}"


def build_index(chunks_dir="data/processed/chunks", qdrant_path="data/qdrant", model=DEFAULT_MODEL):
    emb = get_embedder(model)
    children, parents = load_chunks(chunks_dir)
    vecs = emb.encode([embed_text(c) for c in children])
    client = make_client(qdrant_path)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(COLLECTION, vectors_config=VectorParams(size=int(vecs.shape[1]), distance=Distance.COSINE))
    for i in range(0, len(children), 256):
        client.upsert(COLLECTION, points=[
            PointStruct(id=j, vector=vecs[j].tolist(), payload={**children[j], "idx": j})
            for j in range(i, min(i + 256, len(children)))])
    return client, emb, children, parents


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--path", default="data/qdrant")
    a = ap.parse_args()
    _, _, children, parents = build_index(qdrant_path=a.path, model=a.model)
    Path(a.path).mkdir(parents=True, exist_ok=True)
    (Path(a.path) / "meta.json").write_text(json.dumps({"model": a.model, "children": len(children), "parents": len(parents)}))
    print(f"indexed {len(children)} children, {len(parents)} parents with {a.model} into {a.path}")


if __name__ == "__main__":
    main()