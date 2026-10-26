import re
from pathlib import PureWindowsPath
from urllib.parse import unquote

from fastapi import HTTPException

MAX_FILENAME_LENGTH = 512
MAX_ENCODED_FILENAME_LENGTH = MAX_FILENAME_LENGTH * 12


def upload_filename(legacy: str, encoded: str | None) -> str:
    """Only the opt-in encoded header uses UTF-8 percent decoding, exactly once."""
    value = legacy
    if encoded is not None:
        if (
            len(encoded) > MAX_ENCODED_FILENAME_LENGTH
            or not encoded.isascii()
            or re.search(r"%(?![0-9a-fA-F]{2})", encoded)
        ):
            raise HTTPException(status_code=422, detail="文件名编码无效")
        try:
            value = unquote(encoded, encoding="utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="文件名不是有效的 UTF-8") from exc
    if (
        not value
        or len(value) > MAX_FILENAME_LENGTH
        or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)
    ):
        raise HTTPException(status_code=422, detail="文件名无效或超过 512 字符")
    name = PureWindowsPath(value).name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=422, detail="文件名无效")
    return name
