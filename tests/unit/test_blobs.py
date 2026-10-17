"""P1-01: content-addressed blob store."""

import hashlib
from pathlib import Path

import pytest

from rlg.store.blobs import BlobStore


def test_same_content_stored_once(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    a = store.put(b"hello")
    b = store.put(b"hello")
    assert a.sha256 == b.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert a.created and not b.created
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == [store.path(a.sha256)]
    assert store.get(a.sha256) == b"hello"


def test_different_content_different_blobs(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    assert store.put(b"a").path != store.put(b"b").path


def test_corruption_detected(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    ref = store.put(b"data")
    store.path(ref.sha256).write_bytes(b"changed")
    with pytest.raises(OSError, match="corrupted"):
        store.get(ref.sha256)
