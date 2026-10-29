import Foundation
import AVFoundation

// The Core Audio render thread owns tempo/pitch, independent of Python/MLX.
let engine = AVAudioEngine()
let player = AVAudioPlayerNode()
let tuning = AVAudioUnitTimePitch()
tuning.rate = 1.20
tuning.pitch = 0
tuning.overlap = 16
let format = AVAudioFormat(standardFormatWithSampleRate: 24000, channels: 1)!
engine.attach(player); engine.attach(tuning)
engine.connect(player, to: tuning, format: format)
engine.connect(tuning, to: engine.mainMixerNode, format: format)
if CommandLine.arguments.contains("--silent-test") { engine.mainMixerNode.outputVolume = 0 }

func renderFile(_ input: String, _ output: String) throws {
    let file = try AVAudioFile(forReading: URL(fileURLWithPath: input))
    var settings = format.settings
    settings[AVLinearPCMIsFloatKey] = false
    settings[AVLinearPCMBitDepthKey] = 16
    let destination = try AVAudioFile(forWriting: URL(fileURLWithPath: output), settings: settings)
    try engine.enableManualRenderingMode(.offline, format: format, maximumFrameCount: 4096)
    player.scheduleFile(file, at: nil)
    try engine.start(); player.play()
    let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 4096)!
    let target = AVAudioFramePosition(Double(file.length) * 24000 / file.processingFormat.sampleRate / 1.20)
    var rendered: AVAudioFramePosition = 0
    var attempts = 0
    while rendered < target && attempts < Int(target / 4096) + 100 {
        attempts += 1
        let count = AVAudioFrameCount(min(4096, target-rendered))
        let status = try engine.renderOffline(count, to: buffer)
        if status == .success { try destination.write(from: buffer); rendered += AVAudioFramePosition(buffer.frameLength) }
        else if status == .error { throw NSError(domain: "JarvisAudio", code: 2) }
    }
    engine.stop()
    guard rendered >= target else { throw NSError(domain: "JarvisAudio", code: 3) }
}

func streamInput() throws {
    let capacity = DispatchSemaphore(value: 10)
    let drained = DispatchGroup()
    let lock = NSLock()
    var queued = 0, buffers = 0, underruns = 0
    var inputEnded = false, started = false
    var received = 0
    let began = ProcessInfo.processInfo.systemUptime
    var firstPlay = 0.0
    var pending = Data()
    try engine.start()
    while true {
        let incoming = FileHandle.standardInput.readData(ofLength: 11520 * 4 - pending.count)
        pending.append(incoming)
        if !incoming.isEmpty && pending.count < 11520 * 4 { continue }
        if pending.isEmpty { break }
        let data = pending
        pending.removeAll(keepingCapacity: true)
        let frames = data.count / 4
        guard frames > 0 else { continue }
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames))!
        buffer.frameLength = AVAudioFrameCount(frames)
        _ = data.withUnsafeBytes { raw in
            memcpy(buffer.floatChannelData![0], raw.baseAddress!, frames * 4)
        }
        capacity.wait(); drained.enter()
        lock.lock(); queued += 1; buffers += 1; received += frames; lock.unlock()
        player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { _ in
            lock.lock(); queued -= 1
            if queued == 0 && started && !inputEnded { underruns += 1 }
            lock.unlock()
            capacity.signal(); drained.leave()
        }
        lock.lock()
        let shouldStart = !started && received >= 24000 * 3 / 2
        if shouldStart { started = true; firstPlay = ProcessInfo.processInfo.systemUptime - began }
        lock.unlock()
        if shouldStart { player.play() }
        if incoming.isEmpty { break }
    }
    lock.lock(); inputEnded = true
    let shouldStart = !started && received > 0
    if shouldStart { started = true; firstPlay = ProcessInfo.processInfo.systemUptime - began }
    lock.unlock()
    if shouldStart { player.play() }
    let wait = drained.wait(timeout: .now() + Double(received)/24000 + 10)
    engine.stop()
    guard wait == .success else { throw NSError(domain: "JarvisAudio", code: 4) }
    let stats: [String:Any] = ["buffers":buffers,"underruns":underruns,"samples":received,
        "first_play_seconds":firstPlay,"speed":1.20,"pitch_semitones":0.0,"native":true]
    let json = try JSONSerialization.data(withJSONObject: stats)
    FileHandle.standardError.write(Data("JARVIS_AUDIO ".utf8) + json + Data("\n".utf8))
}

do {
    if CommandLine.arguments.count == 4 && CommandLine.arguments[1] == "--render" {
        try renderFile(CommandLine.arguments[2], CommandLine.arguments[3])
    } else { try streamInput() }
} catch {
    FileHandle.standardError.write(Data("Jarvis audio: \(error)".utf8)); exit(1)
}
