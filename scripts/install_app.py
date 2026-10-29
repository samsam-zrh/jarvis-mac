#!/usr/bin/env python3
"""Installer l'application construite et son lancement discret à la connexion."""
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
source = ROOT / "build/Jarvis.app"
destination = Path.home() / "Applications/Jarvis.app"
if not source.is_dir():
    raise SystemExit("Compiler d'abord : bash scripts/build_app.sh")
if destination.exists():
    existing = plistlib.loads((destination / "Contents/Info.plist").read_bytes())
    if existing.get("CFBundleIdentifier") != "local.samuel.jarvis":
        raise SystemExit("Une autre application Jarvis existe déjà ; elle est conservée.")
destination.parent.mkdir(exist_ok=True)
shutil.copytree(source, destination, dirs_exist_ok=True)
subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(destination)], check=True)
agents = Path.home() / "Library/LaunchAgents"
agents.mkdir(exist_ok=True)
agent = agents / "local.samuel.jarvis.plist"
payload = {"Label": "local.samuel.jarvis", "ProgramArguments": ["/usr/bin/open", "-gj", str(destination)], "RunAtLoad": True}
agent.write_bytes(plistlib.dumps(payload))
os.chmod(agent, 0o600)
target = f"gui/{os.getuid()}"
subprocess.run(["/bin/launchctl", "bootout", target + "/local.samuel.jarvis"], capture_output=True)
result = subprocess.run(["/bin/launchctl", "bootstrap", target, str(agent)], capture_output=True, text=True)
if result.returncode:
    raise SystemExit("Application installée mais lancement à la connexion non enregistré : " + result.stderr)
print("Application installée :", destination)
print("Lancement discret à la connexion enregistré.")
