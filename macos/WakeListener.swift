import Cocoa
import AVFoundation
import Speech

/// Continuous on-device French recognition. No network fallback is permitted.
final class WakeListener {
    var onWake: (() -> Void)?
    var onIdle: (() -> Void)?
    var onCommand: ((String) -> Void)?
    var onCommandAudio: ((String, Data) -> Void)?
    var onInterrupt: (() -> Void)?
    var onStatus: ((String) -> Void)?
    var onLevel: ((Double) -> Void)?
    var onPartialCommand: ((String) -> Void)?
    var onTurnCheck: ((Data, @escaping (Bool?) -> Void) -> Void)?
    var vocabulary: [String] = []
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "fr-FR"))
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var timer: Timer?
    private var settle: DispatchWorkItem?
    private var wakeTimeout: DispatchWorkItem?
    private var generation = UUID()
    private var tapped = false
    private var awake = false
    private var command = ""
    private var lastLevel = 0.0
    private(set) var enabled = false
    private var suspended = false
    private var manuallyPaused = false
    private var recentSamples: [Float] = []
    private var commandSamples: [Float] = []
    private var audioRate: Double = 48000
    private var lastSpeechTime = 0.0
    private var lastTranscriptTime = 0.0
    private var boundaryRevision = UUID()
    private var checkedRevision: UUID?
    private var acousticComplete: Bool?
    private var noiseFloor = 0.002
    private var transcriptPrefix = ""

    func enable() {
        enabled = true
        SFSpeechRecognizer.requestAuthorization { [weak self] authorization in
            AVCaptureDevice.requestAccess(for: .audio) { allowed in
                DispatchQueue.main.async {
                    guard let self = self, self.enabled else { return }
                    guard authorization == .authorized, allowed else {
                        self.onStatus?("Autorisez le microphone et la reconnaissance vocale pour Jarvis dans Réglages Système."); return
                    }
                    guard self.recognizer?.supportsOnDeviceRecognition == true else {
                        self.onStatus?("La reconnaissance française locale d’Apple n’est pas disponible. La dictée au bouton reste utilisable."); return
                    }
                    self.start()
                }
            }
        }
    }

    func disable() { enabled = false; stop(); onStatus?("Écoute vocale désactivée") }

    func suspend(_ value: Bool) {
        guard suspended != value else { return }
        suspended = value
        if enabled && !engine.isRunning { start() }
    }

    func pauseForManual(_ value: Bool) {
        manuallyPaused = value
        if value { stop() } else if enabled { start() }
    }

    private func stop(endListening: Bool = true) {
        if awake && endListening { onIdle?() }
        generation = UUID()
        settle?.cancel(); wakeTimeout?.cancel(); timer?.invalidate()
        engine.stop()
        if tapped { engine.inputNode.removeTap(onBus: 0); tapped = false }
        request?.endAudio(); task?.cancel(); task = nil; request = nil
        awake = false; command = ""
        transcriptPrefix = ""
        boundaryRevision = UUID(); checkedRevision = nil; acousticComplete = nil
        recentSamples.removeAll(keepingCapacity: true)
        commandSamples.removeAll(keepingCapacity: true)
    }

    private func start(continuing: Bool = false) {
        guard enabled, !manuallyPaused, SFSpeechRecognizer.authorizationStatus() == .authorized,
              AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else { return }
        let savedCommand = command, savedSamples = commandSamples
        let savedSpeech = lastSpeechTime, savedTranscript = lastTranscriptTime
        stop(endListening: !continuing)
        if continuing {
            awake = true; command = savedCommand; transcriptPrefix = savedCommand
            commandSamples = savedSamples
            lastSpeechTime = savedSpeech; lastTranscriptTime = savedTranscript
        }
        guard let recognizer = recognizer, recognizer.supportsOnDeviceRecognition, recognizer.isAvailable else {
            onStatus?("Reconnaissance locale indisponible. Réessayez l’écoute vocale dans le menu Jarvis."); return
        }
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = true
        request.contextualStrings = ["Jarvis", "Spotify", "l’intelligence artificielle", "Jarvis ouvre", "Jarvis crée", "Jarvis cherche"] + vocabulary
        request.taskHint = .dictation
        self.request = request
        let node = engine.inputNode
        let format = node.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else { onStatus?("Aucun microphone disponible"); return }
        node.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            request.append(buffer)
            if let samples = buffer.floatChannelData?[0] {
                let count = Int(buffer.frameLength)
                var square = 0.0
                for i in 0..<count { square += Double(samples[i] * samples[i]) }
                let level = min(1.0, sqrt(square / Double(max(count, 1))) * 12)
                let copied = Array(UnsafeBufferPointer(start: samples, count: count))
                DispatchQueue.main.async {
                    guard let self = self else { return }
                    self.audioRate = format.sampleRate
                    self.recentSamples.append(contentsOf: copied)
                    let excess = self.recentSamples.count - Int(format.sampleRate)
                    if excess > 0 { self.recentSamples.removeFirst(excess) }
                    let rms = level / 12
                    if !self.awake {
                        self.noiseFloor = min(0.015, self.noiseFloor * 0.98 + rms * 0.02)
                        return
                    }
                    if rms > max(0.004, self.noiseFloor * 2.5) {
                        self.lastSpeechTime = ProcessInfo.processInfo.systemUptime
                        self.acousticComplete = nil; self.checkedRevision = nil
                        self.boundaryRevision = UUID()
                    }
                    if self.commandSamples.count < Int(format.sampleRate * 90) { self.commandSamples.append(contentsOf: copied) }
                    let now = ProcessInfo.processInfo.systemUptime
                    if now - self.lastLevel > 0.08 { self.lastLevel = now; self.onLevel?(level) }
                }
            }
        }
        tapped = true
        let current = generation
        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            DispatchQueue.main.async {
                guard let self = self, self.generation == current else { return }
                if let result = result { self.receive(result.bestTranscription.formattedString) }
                if error != nil || result?.isFinal == true {
                    if self.awake && !self.command.isEmpty {
                        // Apple's segment boundaries are not the user's turn boundaries.
                        self.start(continuing: true); self.scheduleBoundary()
                    }
                    else { self.restart(after: 1) }
                }
            }
        }
        do {
            engine.prepare(); try engine.start()
            onStatus?("Dites « Jarvis »")
            timer = Timer.scheduledTimer(withTimeInterval: 48, repeats: false) { [weak self] _ in
                guard let self = self else { return }
                if self.awake && !self.command.isEmpty { self.start(continuing: true); self.scheduleBoundary() }
                else { self.restart(after: 0.1) }
            }
        } catch { stop(); onStatus?("Microphone indisponible : \(error.localizedDescription)") }
    }

    func receive(_ transcript: String) {
        guard let extracted = WakePhrase.command(in: transcript) ?? (awake ? transcript.trimmingCharacters(in: .whitespacesAndNewlines) : nil) else { return }
        if suspended {
            // During speech keep only wake detection active, so the user can
            // interrupt without waiting for the current answer to finish.
            suspended = false
            onInterrupt?()
        }
        if !awake {
            commandSamples = recentSamples
            awake = true; onWake?()
            let timeout = DispatchWorkItem { [weak self] in self?.restart(after: 0.1) }
            wakeTimeout = timeout
            DispatchQueue.main.asyncAfter(deadline: .now() + 15, execute: timeout)
        }
        let combined = transcriptPrefix.isEmpty ? extracted : transcriptPrefix + " " + extracted
        if combined == command && !command.isEmpty { return }
        command = combined
        lastTranscriptTime = ProcessInfo.processInfo.systemUptime
        boundaryRevision = UUID(); checkedRevision = nil; acousticComplete = nil
        if !command.isEmpty { wakeTimeout?.cancel() }
        onPartialCommand?(command)
        scheduleBoundary()
    }

    private func scheduleBoundary() {
        settle?.cancel()
        guard !command.isEmpty else { return }
        let work = DispatchWorkItem { [weak self] in self?.checkBoundary() }
        settle = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12, execute: work)
    }

    private func checkBoundary() {
        guard awake, !command.isEmpty else { return }
        let silence = ProcessInfo.processInfo.systemUptime - max(lastSpeechTime, lastTranscriptTime)
        if silence >= 0.95, checkedRevision != boundaryRevision,
           let check = onTurnCheck, let audio = commandWAV(lastSeconds: 8) {
            let revision = boundaryRevision
            checkedRevision = revision
            check(audio) { [weak self] complete in
                guard let self = self, self.awake, self.boundaryRevision == revision else { return }
                self.acousticComplete = complete
            }
        }
        if TurnBoundary.shouldSubmit(text: command, silence: silence, acousticComplete: acousticComplete) {
            submit()
        } else { scheduleBoundary() }
    }

    private func submit() {
        let text = command
        let audio = commandWAV()
        stop(endListening: false)
        if !text.isEmpty {
            suspended = true
            if let audio = audio, let handler = onCommandAudio { handler(text, audio) } else { onCommand?(text) }
            start()
        }
        else { start() }
    }

    private func commandWAV(lastSeconds: Double? = nil) -> Data? {
        guard commandSamples.count > Int(audioRate * 0.2) else { return nil }
        let samples = lastSeconds.map { Array(commandSamples.suffix(Int(audioRate * $0))) } ?? commandSamples
        let pcm = samples.map { Int16(max(-1, min(1, $0)) * 32767) }
        var data = Data()
        func u16(_ value: UInt16) { var n = value.littleEndian; withUnsafeBytes(of: &n) { data.append(contentsOf: $0) } }
        func u32(_ value: UInt32) { var n = value.littleEndian; withUnsafeBytes(of: &n) { data.append(contentsOf: $0) } }
        data.append(Data("RIFF".utf8)); u32(UInt32(36 + pcm.count * 2))
        data.append(Data("WAVEfmt ".utf8)); u32(16); u16(1); u16(1)
        u32(UInt32(audioRate)); u32(UInt32(audioRate) * 2); u16(2); u16(16)
        data.append(Data("data".utf8)); u32(UInt32(pcm.count * 2))
        pcm.withUnsafeBytes { data.append(contentsOf: $0) }
        return data
    }

    private func restart(after seconds: Double) {
        stop()
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { [weak self] in self?.start() }
    }
}
