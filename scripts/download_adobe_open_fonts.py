import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FONTS_DIR = ROOT / "fonts" / "open"
MANIFEST_PATH = FONTS_DIR / "open_fonts_manifest.json"
CACHE_DIR = Path(tempfile.gettempdir()) / "subtitle_composer_adobe_fonts"


ADOBE_OPEN_FONTS = [
    {
        "family": "Source Han Sans SC",
        "asset_url": "https://github.com/adobe-fonts/source-han-sans/releases/download/2.005R/09_SourceHanSansSC.zip",
        "repo_license": "https://raw.githubusercontent.com/adobe-fonts/source-han-sans/release/LICENSE.txt",
        "license_name": "LICENSE.txt",
        "target_dir": "sourcehansanssc",
        "source": "Adobe Source Han Sans",
        "version": "2.005R",
        "extract": [
            {"contains": "SourceHanSansSC-Regular.otf", "weight": "400"},
            {"contains": "SourceHanSansSC-Bold.otf", "weight": "700"},
        ],
    },
    {
        "family": "Source Han Serif SC",
        "asset_url": "https://github.com/adobe-fonts/source-han-serif/releases/download/2.003R/09_SourceHanSerifSC.zip",
        "repo_license": "https://raw.githubusercontent.com/adobe-fonts/source-han-serif/release/LICENSE.txt",
        "license_name": "LICENSE.txt",
        "target_dir": "sourcehanserifsc",
        "source": "Adobe Source Han Serif",
        "version": "2.003R",
        "extract": [
            {"contains": "SourceHanSerifSC-Regular.otf", "weight": "400"},
            {"contains": "SourceHanSerifSC-Bold.otf", "weight": "700"},
        ],
    },
    {
        "family": "Source Sans 3",
        "asset_url": "https://github.com/adobe-fonts/source-sans/releases/download/3.052R/VF-source-sans-3.052R.zip",
        "repo_license": "https://raw.githubusercontent.com/adobe-fonts/source-sans/release/LICENSE.md",
        "license_name": "LICENSE.md",
        "target_dir": "sourcesans3",
        "source": "Adobe Source Sans 3",
        "version": "3.052R",
        "extract": [
            {"contains": "SourceSans3VF-Upright.ttf", "weight": "200 900"},
        ],
    },
    {
        "family": "Source Serif 4",
        "asset_url": "https://github.com/adobe-fonts/source-serif/releases/download/4.005R/source-serif-4.005_Desktop.zip",
        "repo_license": "https://raw.githubusercontent.com/adobe-fonts/source-serif/release/LICENSE.md",
        "license_name": "LICENSE.md",
        "target_dir": "sourceserif4",
        "source": "Adobe Source Serif 4",
        "version": "4.005R",
        "extract": [
            {"contains": "SourceSerif4Variable-Roman.ttf", "weight": "200 900"},
        ],
    },
    {
        "family": "Source Code Pro",
        "asset_url": "https://github.com/adobe-fonts/source-code-pro/releases/download/2.042R-u/1.062R-i/1.026R-vf/VF-source-code-VF-1.026R.zip",
        "repo_license": "https://raw.githubusercontent.com/adobe-fonts/source-code-pro/release/LICENSE.md",
        "license_name": "LICENSE.md",
        "target_dir": "sourcecodepro",
        "source": "Adobe Source Code Pro",
        "version": "2.042R-u/1.062R-i/1.026R-vf",
        "extract": [
            {"contains": "SourceCodeVF-Upright.ttf", "weight": "200 900"},
        ],
    },
]


def request(url):
    return urllib.request.Request(url, headers={"User-Agent": "Subtitle-Composer-adobe-font-pack/1.0"})


def download(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return target
    with urllib.request.urlopen(request(url), timeout=180) as response:
        with target.open("wb") as output:
            shutil.copyfileobj(response, output)
    return target


def load_manifest():
    if not MANIFEST_PATH.exists():
        return {"schema": 1, "fonts": []}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": 1, "fonts": []}


def save_manifest(manifest):
    manifest["schema"] = 1
    manifest["fonts"] = sorted(
        manifest.get("fonts", []),
        key=lambda item: (str(item.get("family", "")).casefold(), str(item.get("file", "")).casefold()),
    )
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_manifest_record(manifest, record):
    fonts = manifest.setdefault("fonts", [])
    key = (record["family"].casefold(), record["file"].casefold())
    for index, old in enumerate(fonts):
        old_key = (str(old.get("family", "")).casefold(), str(old.get("file", "")).casefold())
        if old_key == key:
            merged = dict(old)
            merged.update(record)
            fonts[index] = merged
            return
    fonts.append(record)


def safe_member_name(name):
    return os.path.basename(str(name or "").replace("\\", "/"))


def find_zip_member(zip_obj, needle):
    needle_key = str(needle or "").casefold()
    candidates = [
        name for name in zip_obj.namelist()
        if needle_key in name.casefold() and not name.endswith("/")
    ]
    if not candidates:
        raise FileNotFoundError(f"Could not find {needle} in {zip_obj.filename}")
    return sorted(candidates, key=lambda item: (len(item), item.casefold()))[0]


def extract_font(zip_obj, member_name, target_dir):
    filename = safe_member_name(member_name)
    target = target_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    with zip_obj.open(member_name) as source, target.open("wb") as output:
        shutil.copyfileobj(source, output)
    return target


def main():
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    extracted = 0

    for font in ADOBE_OPEN_FONTS:
        family = font["family"]
        print(f"Scanning {family}...")
        target_dir = FONTS_DIR / font["target_dir"]
        target_dir.mkdir(parents=True, exist_ok=True)

        license_target = target_dir / font["license_name"]
        download(font["repo_license"], license_target)
        license_rel = license_target.relative_to(FONTS_DIR).as_posix()

        zip_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", font["asset_url"].rsplit("/", 1)[-1])
        zip_path = download(font["asset_url"], CACHE_DIR / zip_name)
        with zipfile.ZipFile(zip_path) as zip_obj:
            for item in font["extract"]:
                member = find_zip_member(zip_obj, item["contains"])
                target = extract_font(zip_obj, member, target_dir)
                print(f"  extracted {target.name}")
                upsert_manifest_record(manifest, {
                    "family": family,
                    "file": target.relative_to(FONTS_DIR).as_posix(),
                    "source": font["source"],
                    "version": font["version"],
                    "license": "OFL-1.1",
                    "license_file": license_rel,
                    "license_url": "https://scripts.sil.org/OFL",
                    "weight": item.get("weight", "400"),
                    "style": item.get("style", "normal"),
                    "notes": "Downloaded from Adobe's official open-source font GitHub releases. Commercial use is allowed under the SIL Open Font License; keep the license file with redistributed font files.",
                    "downloaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                extracted += 1

    save_manifest(manifest)
    print(f"Done. Extracted {extracted} Adobe open font file(s). Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Adobe font download failed: {exc}", file=sys.stderr)
        sys.exit(1)
