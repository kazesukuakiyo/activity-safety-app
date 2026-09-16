"""添付ファイルの保管。8.1-6 添付振分け / 9. 個人情報分離。

- 行程等・その他   → data/activity_docs/         (課外活動申請サイト「活動資料」相当)
- 参加者名簿・年度部員名簿 → data/personal_info_vault/ (個人情報管理サイト相当。閲覧は職員・管理職に限定)
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from ..config import settings
from ..models import AttachmentKind

_SAFE = re.compile(r"[^A-Za-z0-9._\-ぁ-んァ-ヶ一-龠々ー]+")


def safe_filename(name: str) -> str:
    name = Path(name or "file").name
    name = _SAFE.sub("_", name).strip("._") or "file"
    return name[:120]


def is_restricted(kind: AttachmentKind) -> bool:
    return kind == AttachmentKind.ROSTER


def target_dir(kind: AttachmentKind) -> Path:
    return settings.roster_vault_dir if is_restricted(kind) else settings.activity_docs_dir


def save_attachment(kind: AttachmentKind, application_no: str, original_name: str, data: bytes) -> tuple[str, Path]:
    """ファイルを保管先に保存し (相対パス, 絶対パス) を返す。"""
    base = target_dir(kind)
    folder = base / application_no
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex[:8]}_{safe_filename(original_name)}"
    path = folder / stored_name
    path.write_bytes(data)
    return str(path.relative_to(settings.data_dir)), path


def save_roster_file(org_code: str, fiscal_year: int, original_name: str, data: bytes) -> tuple[str, Path]:
    """年度部員名簿。活動届とは別フォルダの限定保管先に置く。"""
    folder = settings.roster_vault_dir / "annual" / str(fiscal_year) / org_code
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
