"""Chroma client factory.

Returns a remote HttpClient when CHROMA_HOST is set in the environment,
otherwise falls back to a local PersistentClient at the given palace_path.
This lets the same code run against a local on-disk palace (CLI usage)
or against a dedicated chromadb container (compose deployment).
"""

import os

import chromadb


def get_chroma_client(palace_path: str | None = None):
    host = os.environ.get("CHROMA_HOST")
    if host:
        port = int(os.environ.get("CHROMA_PORT", "8000"))
        return chromadb.HttpClient(host=host, port=port)
    if not palace_path:
        raise ValueError(
            "palace_path is required when CHROMA_HOST is not set"
        )
    return chromadb.PersistentClient(path=palace_path)
