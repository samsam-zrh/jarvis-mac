#!/usr/bin/env python3
"""Reproduce the pinned local voice, turn detector and native Core Audio runtime."""
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def download(url, path, digest=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and (not digest or hashlib.sha256(path.read_bytes()).hexdigest()==digest): return
    temporary=path.with_suffix(path.suffix+'.partial')
    urllib.request.urlretrieve(url,temporary)
    if digest and hashlib.sha256(temporary.read_bytes()).hexdigest()!=digest:
        raise RuntimeError('Empreinte incorrecte : '+str(path))
    temporary.replace(path)


def main():
    manifest=json.loads((ROOT/'Documents/modele-voix-naturelle.json').read_text())
    for item in manifest['files']:
        download('https://huggingface.co/'+manifest['repo']+'/resolve/'+manifest['revision']+'/'+item['path'],
                 ROOT/'.runtime/qwen-voice-design'/item['path'], item.get('sha256'))
    turn=json.loads((ROOT/'Documents/modele-fin-de-phrase.json').read_text())
    download('https://huggingface.co/'+turn['repository']+'/resolve/'+turn['revision']+'/'+turn['file'],
             ROOT/'.runtime/smart-turn/model.onnx',turn['sha256'])
    subprocess.run(['/usr/bin/swiftc','-O','-framework','AVFoundation',
        str(ROOT/'macos/VoicePlayer.swift'),'-o',str(ROOT/'.runtime/voice-player')],check=True)
    print('Voix, détection de fin de phrase et traitement continu prêts, entièrement locaux.')


if __name__=='__main__': main()
