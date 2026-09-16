"""添付ファイル (行程表・大会要項など) の保管。data/activity_docs/ に活動届ごとのフォルダで置く。

名簿はファイルとして受け取らない (models.Member / models.Participant に表として保持する)。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from ..config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._\-ぁ-んァ-ヶ一-龠々ー]+")


def safe_filename(name: str) -> str:
    name = Path(name or "file").name
    name = _SAFE.sub("_", name).strip("._") or "file"
    return name[:120]


def save_attachment(application_no: str, original_name: str, data: bytes) -> tuple[str, Path]:
    """ファイルを保存し (相対パス, 絶対パス) を返す。"""
    folder = settings.activity_docs_dir / application_no
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex[:8]}_{safe_filename(original_name)}"
    path = folder / stored_name
    path.write_bytes(data)
    return str(path.relative_to(settings.data_dir)), path


def resolve(stored_path: str) -> Path:
    path = (settings.data_dir / stored_path).resolve()
    if settings.data_dir not in path.parents:
        raise ValueError("不正なパスです")
    return path


def delete_file(stored_path: str) -> None:
    try:
        resolve(stored_path).unlink(missing_ok=True)
    except ValueError:
        pass
