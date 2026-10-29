#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$PROJECT_ROOT/build/Jarvis.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
mkdir -p "$PROJECT_ROOT/.runtime"
/usr/bin/swiftc -O -framework AVFoundation "$PROJECT_ROOT/macos/VoicePlayer.swift" -o "$PROJECT_ROOT/.runtime/voice-player"
/usr/bin/swiftc -O -framework Cocoa -framework WebKit -framework AVFoundation -framework Speech "$PROJECT_ROOT/macos/WakePhrase.swift" "$PROJECT_ROOT/macos/WakeListener.swift" "$PROJECT_ROOT/macos/Jarvis.swift" "$PROJECT_ROOT/macos/Background.swift" -o "$APP/Contents/MacOS/Jarvis"
printf '%s' "$PROJECT_ROOT" > "$APP/Contents/Resources/project.txt"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>Jarvis</string>
<key>CFBundleIdentifier</key><string>local.samuel.jarvis</string>
<key>CFBundleName</key><string>Jarvis</string>
<key>CFBundleDisplayName</key><string>Jarvis</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>0.1.0</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSMicrophoneUsageDescription</key><string>Jarvis enregistre votre demande pour la transcrire localement sur votre Mac.</string>
<key>NSAppleEventsUsageDescription</key><string>Jarvis utilise les applications de votre Mac pour accomplir vos demandes.</string>
<key>NSHighResolutionCapable</key><true/>
<key>LSUIElement</key><true/>
<key>NSSpeechRecognitionUsageDescription</key><string>Jarvis reconnaît localement son nom et vos demandes pour vous répondre sans ouvrir sa fenêtre.</string>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST
/usr/bin/codesign --force --sign - "$APP"
printf 'Application compilée : %s\n' "$APP"
