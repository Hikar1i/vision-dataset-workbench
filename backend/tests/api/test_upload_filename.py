from urllib.parse import quote

import pytest
from fastapi import HTTPException

from vision_dataset_workbench.api.upload_filename import upload_filename


@pytest.mark.parametrize(
    "original, expected",
    [
        ("中文 图像😀 100% + #.png", "中文 图像😀 100% + #.png"),
        ("/a/图像.png", "图像.png"),
        (r"C:\fakepath\视频.mp4", "视频.mp4"),
        (r"../a\测试集.zip", "测试集.zip"),
        ("%2F.png", "%2F.png"),
        ("😀" * 508 + ".png", "😀" * 508 + ".png"),
    ],
)
def test_encoded_filename_is_decoded_once_and_reduced_to_basename(original, expected):
    assert upload_filename("fallback", quote(original, safe="")) == expected


@pytest.mark.parametrize("name", ["100%.png", "%2F.png", "%E4%B8%AD.zip", "sample.png"])
def test_legacy_header_remains_literal(name):
    assert upload_filename(name, None) == name


@pytest.mark.parametrize(
    "encoded",
    [
        "bad%",
        "bad%2",
        "%GG.png",
        "%FF.png",
        "%ED%A0%80.png",
        "中文.png",
        "%00.png",
        "bad%0D%0AX-Test%3Aevil.png",
        "%1F.png",
        "%7F.png",
        "%C2%85.png",
        "%C0%AF.png",
        "",
        ".",
        "..",
        "%2F",
        "a" * 513,
        quote("😀" * 509 + ".png"),
    ],
)
def test_invalid_encoded_filename_is_rejected(encoded):
    with pytest.raises(HTTPException) as error:
        upload_filename("fallback", encoded)
    assert error.value.status_code == 422


@pytest.mark.parametrize("name", ["bad\r\n.png", "bad\x00.png", "", ".", "..", "x" * 513])
def test_invalid_legacy_filename_is_rejected(name):
    with pytest.raises(HTTPException) as error:
        upload_filename(name, None)
    assert error.value.status_code == 422
