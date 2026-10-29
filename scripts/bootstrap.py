#!/usr/bin/env python3
"""Récupération reproductible des moteurs officiels épinglés et vérifiés."""
import hashlib
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = [
    ("goose", "goose.tar.gz", "https://github.com/aaif-goose/goose/releases/download/v1.56.0/goose-aarch64-apple-darwin.tar.gz", "52f3f8d62e3d144c5de70c5c471de39d8b92c24d41d5b3436eb8bab11ba4bc24"),
    ("ollama", "ollama.tgz", "https://github.com/ollama/ollama/releases/download/v0.40.12/ollama-darwin.tgz", "1d1b4c2cf40d2a239f9b08a77384830800a8542c744a55f47247f9baf85b55d2"),
    ("cua", "cua.tar.gz", "https://github.com/trycua/cua/releases/download/cua-driver-rs-v0.37.0/cua-driver-rs-0.37.0-darwin-arm64.tar.gz", "1e9b8c58cc830e080ada881ec76286529f5f1264fe9ecc371b0ae95cff98928b"),
]
for name, filename, url, digest in ARTIFACTS:
    archive = ROOT / ".runtime/downloads" / filename
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_suffix(".partial")
        urllib.request.urlretrieve(url, temporary)
        temporary.replace(archive)
    with archive.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != digest:
        raise SystemExit("Empreinte incorrecte : " + filename)
    target = ROOT / ".runtime" / name
    target.mkdir(exist_ok=True)
    with tarfile.open(archive) as package:
        package.extractall(target, filter="data")
    print(name, "vérifié et extrait")
print("Installer ensuite les dépendances avec uv pip sync --python .venv/bin/python requirements.lock.")
print("CuaDriver.app doit être installé depuis l’archive signée dans /Applications, sans remplacer une autre installation sans vérification.")
