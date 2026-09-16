"""名簿 (4 列の表) の取り込みと検証。

学生は Excel からコピーして貼り付けるだけでよい。1 行 1 人、列はタブ・カンマ・全角カンマ区切り。
    学籍番号  氏名  所属  学年
列数が 4 でない行は受け付けない (要配慮情報などの余計な列を持ち込ませないため)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED_COLUMNS = ("学籍番号", "氏名", "所属", "学年")
_SPLIT = re.compile(r"\t|,|、|，")
MAX_ROWS = 500


@dataclass(frozen=True)
class RosterRow:
    student_no: str
    name: str
    department: str
    grade: str

    def as_line(self) -> str:
        return "\t".join((self.student_no, self.name, self.department, self.grade))


class RosterError(ValueError):
    pass


def parse_roster_text(text: str) -> list[RosterRow]:
    """貼り付けテキストを解析して行のリストにする。不正な行があれば RosterError。"""
    rows: list[RosterRow] = []
    errors: list[str] = []
    seen: set[str] = set()
    for lineno, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        cols = [c.strip() for c in _SPLIT.split(line)]
        # 末尾の空セル (Excel の余白列) は無視する
        while cols and cols[-1] == "":
            cols.pop()
        if cols[:4] == list(ALLOWED_COLUMNS):
            continue  # 見出し行はスキップ
        if len(cols) != 4:
            errors.append(f"{lineno} 行目: 列数が {len(cols)} です。学籍番号・氏名・所属・学年 の 4 列にしてください")
            continue
        if any(c == "" for c in cols):
            errors.append(f"{lineno} 行目: 空欄があります")
            continue
        row = RosterRow(*cols)
        if row.student_no in seen:
            errors.append(f"{lineno} 行目: 学籍番号 {row.student_no} が重複しています")
            continue
        seen.add(row.student_no)
        rows.append(row)
    if len(rows) > MAX_ROWS:
        errors.append(f"名簿は {MAX_ROWS} 人までです")
    if errors:
        raise RosterError("\n".join(errors))
    return rows


def rows_to_text(rows) -> str:
    """DB の行 (Member / Participant) を貼り付け欄に戻すためのテキストにする。"""
    return "\n".join("\t".join((r.student_no, r.name, r.department, r.grade)) for r in rows)


def merge(*groups: list[RosterRow]) -> list[RosterRow]:
    """複数の入力元 (部員一覧からの選択 + 貼り付け) を学籍番号で重複除去して結合する。"""
    out: list[RosterRow] = []
    seen: set[str] = set()
    for g in groups:
        for r in g:
            if r.student_no not in seen:
                seen.add(r.student_no)
                out.append(r)
    return out


def to_csv(rows) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(ALLOWED_COLUMNS)
    for r in rows:
        w.writerow((r.student_no, r.name, r.department, r.grade))
    return "﻿" + buf.getvalue()  # BOM 付き (Excel で文字化けしない)
