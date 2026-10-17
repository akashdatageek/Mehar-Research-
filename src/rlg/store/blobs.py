"""Content-addressed blob store on local disk: <root>/<sha[:2]>/<sha[2:4]>/<sha>.

Identical content is stored once. Writes are atomic (temp file + rename).
"""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BlobRef:
    sha256: str
    path: str  # relative to the store root; goes into raw_document.blob_path
    bytes: int
    created: bool  # False when the content was already stored


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def relpath(sha256: str) -> str:
        return f"{sha256[:2]}/{sha256[2:4]}/{sha256}"

    def path(self, sha256: str) -> Path:
        return self.root / self.relpath(sha256)

    def exists(self, sha256: str) -> bool:
        return self.path(sha256).exists()

    def put(self, data: bytes) -> BlobRef:
        """Store `data` once; return its reference."""
        sha = hashlib.sha256(data).hexdigest()
        dest = self.path(sha)
        if dest.exists():
            return BlobRef(sha, self.relpath(sha), len(data), created=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return BlobRef(sha, self.relpath(sha), len(data), created=True)

    def get(self, sha256: str) -> bytes:
        data = self.path(sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise OSError(f"blob {sha256} is corrupted")
        return data
