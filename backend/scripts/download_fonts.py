"""Script to download Google Noto Sans multilingual fonts (OFL-1.1)."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

FONTS: dict[str, str] = {
    "NotoSans-Regular.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
    "NotoSans-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
    "NotoSansDevanagari-Regular.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf",
    "NotoSansDevanagari-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf",
    "NotoSansTamil-Regular.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTamil/NotoSansTamil-Regular.ttf",
    "NotoSansTamil-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTamil/NotoSansTamil-Bold.ttf",
}


def download_fonts(target_dir: Path | None = None) -> None:
    dest = target_dir or Path(__file__).resolve().parent.parent / "assets" / "fonts"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Noto fonts into {dest}...")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for filename, url in FONTS.items():
        out_file = dest / filename
        if out_file.exists() and out_file.stat().st_size > 1000:
            print(f"  [Exists] {filename}")
            continue

        print(f"  Downloading {filename}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response, open(out_file, "wb") as f:
                f.write(response.read())
            print(f"  [Downloaded] {filename} ({out_file.stat().st_size // 1024} KB)")
        except Exception as e:
            print(f"  [Error] Failed to download {filename}: {e}", file=sys.stderr)

    print("Font download complete.")


if __name__ == "__main__":
    download_fonts()
