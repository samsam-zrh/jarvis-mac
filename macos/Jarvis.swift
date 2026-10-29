import Cocoa
import WebKit
import AVFoundation
import Speech

final class JarvisApp: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate, AVAudioRecorderDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process?
    var recorder: AVAudioRecorder?
    var recordingURL: URL?
    var statusItem: NSStatusItem!
    var timer: Timer?
    var localMonitor: Any?
    var globalMonitor: Any?
    var ready = false
    var attempt = 0
    var project: URL!
    var overlay: NSPanel!
    var overlayWeb: WKWebView!
    var overlayNotchWidth: CGFloat = 179
    var overlayNotchHeight: CGFloat = 32
    var overlayScreenObserver: NSObjectProtocol?
    let voiceIndicator = VoiceIndicator(frame: NSRect(x: 14, y: 66, width: 32, height: 32))
    var overlayReadDelay: TimeInterval = 12
    var overlayHeld = false
    var overlayHide: DispatchWorkItem?
    var overlayVisibilityEpoch = 0
    var activityTimer: Timer?
    var lastBackgroundTask = ""
    var backgroundBusy = false
    var manualVoiceBusy = false
    var interruptingSpeech = false
    var pendingVoiceCommand: (String, Data?)?
    let wake = WakeListener()
    var voiceMenuItem: NSMenuItem!
    var listeningEnabled = UserDefaults.standard.object(forKey: "voiceEnabled") == nil || UserDefaults.standard.bool(forKey: "voiceEnabled")

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let config = Bundle.main.url(forResource: "project", withExtension: "txt"),
              let path = try? String(contentsOf: config, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines) else { return }
        project = URL(fileURLWithPath: path)
        makeMenu()
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.add(self, name: "jarvis")
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        web = WKWebView(frame: .zero, configuration: configuration)
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1120, height: 790), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Jarvis"
        window.minSize = NSSize(width: 760, height: 620)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.appearance = NSAppearance(named: .darkAqua)
        let windowGlass = NSVisualEffectView(frame: NSRect(x: 0,y: 0,width:1120,height:790))
        windowGlass.material = .underWindowBackground
        windowGlass.blendingMode = .behindWindow
        windowGlass.state = .active
        web.frame = windowGlass.bounds
        web.autoresizingMask = [.width,.height]
        windowGlass.addSubview(web)
        window.contentView = windowGlass
        window.center()
        window.isReleasedWhenClosed = false
        makeOverlay()
        let loading = "<html><body style='background:#141c23;color:#c4d6dd;font:16px -apple-system;display:grid;place-content:center;height:90vh;text-align:center'><div style='font-size:40px;color:#9cd7d7'>j.</div><p>Jarvis démarre sur votre Mac…</p></body></html>"
        web.loadHTMLString(loading, baseURL: nil)
        startServer()
        timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in self?.connect() }
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "◈"
        statusItem.button?.toolTip = "Jarvis · ⌘ ⇧ Espace pour parler"
        let statusMenu = NSMenu()
        statusMenu.addItem(withTitle: "Ouvrir Jarvis", action: #selector(showWindow), keyEquivalent: "")
        statusMenu.addItem(withTitle: "Parler à Jarvis", action: #selector(recordShortcut), keyEquivalent: "")
        voiceMenuItem = NSMenuItem(title: "Écoute vocale « Jarvis »", action: #selector(toggleVoice), keyEquivalent: "")
        voiceMenuItem.state = listeningEnabled ? .on : .off
        statusMenu.addItem(voiceMenuItem)
        configureWake()
        statusMenu.addItem(.separator())
        statusMenu.addItem(withTitle: "Quitter Jarvis", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        statusItem.menu = statusMenu
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 49 && event.modifierFlags.intersection(.deviceIndependentFlagsMask).contains([.command, .shift]) {
                self?.recordShortcut(); return nil
            }
            return event
        }
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 49 && event.modifierFlags.intersection(.deviceIndependentFlagsMask).contains([.command, .shift]) { self?.recordShortcut() }
        }
    }

    func makeMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Réglages…", action: #selector(openSettings), keyEquivalent: ",")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quitter Jarvis", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        let editItem = NSMenuItem(); main.addItem(editItem)
        let edit = NSMenu(title: "Édition")
        edit.addItem(withTitle: "Annuler", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Couper", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copier", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Coller", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Tout sélectionner", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        NSApp.mainMenu = main
    }

    func startServer() {
        let process = Process()
        process.executableURL = project.appendingPathComponent(".venv/bin/python")
        process.arguments = [project.appendingPathComponent("scripts/launch.py").path]
        process.currentDirectoryURL = project
        let logs = project.appendingPathComponent(".state")
        try? FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
        let logURL = logs.appendingPathComponent("server.log")
        if !FileManager.default.fileExists(atPath: logURL.path) { FileManager.default.createFile(atPath: logURL.path, contents: nil) }
        let log = try? FileHandle(forWritingTo: logURL)
        log?.seekToEndOfFile()
        process.standardOutput = log; process.standardError = log
        do { try process.run(); server = process } catch { showError("Le moteur local ne démarre pas : \(error.localizedDescription)") }
    }

    func connect() {
        guard !ready else { return }
        attempt += 1
        if attempt > 120 { timer?.invalidate(); showError("Le moteur met trop de temps à démarrer. Consultez .state/server.log dans le dossier du projet."); return }
        let tokenURL = project.appendingPathComponent(".state/token")
        guard let token = try? String(contentsOf: tokenURL, encoding: .utf8), !token.isEmpty else { return }
        let base = URL(string: "http://127.0.0.1:8766/")!
        URLSession.shared.dataTask(with: base) { [weak self] _, response, _ in
            guard let response = response as? HTTPURLResponse, response.statusCode == 200 else { return }
            DispatchQueue.main.async {
                guard let self = self, !self.ready else { return }
                self.ready = true; self.timer?.invalidate()
                var components = URLComponents(url: base, resolvingAgainstBaseURL: false)!
                components.fragment = "token=" + token.trimmingCharacters(in: .whitespacesAndNewlines)
                self.web.load(URLRequest(url: components.url!))
                components.path = "/overlay"
                self.overlayWeb.load(URLRequest(url: components.url!))
                self.activityTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in self?.monitorActivity() }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                    if let data = try? Data(contentsOf: self.project.appendingPathComponent(".state/app-vocabulary.json")), let names = try? JSONDecoder().decode([String].self, from: data) { self.wake.vocabulary = names }
                    if self.listeningEnabled { self.wake.enable() }
                }
            }
        }.resume()
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.scheme == "about" || (url.host == "127.0.0.1" && url.port == 8766) { decisionHandler(.allow); return }
        if navigationAction.navigationType == .linkActivated && ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        decisionHandler(.cancel)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if webView === overlayWeb { configureNotch() }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, message.frameInfo.request.url?.host == "127.0.0.1",
              let body = message.body as? [String: Any], let action = body["action"] as? String else { return }
        switch action {
        case "record": toggleRecording()
        case "expand": showWindow()
        case "resize":
            if let size = body["value"] as? [String:Any], let height = size["height"] as? Double { resizeOverlay(height: height, width: size["width"] as? Double) }
        case "hold":
            overlayHeld = body["value"] as? Bool ?? false
            if overlayHeld { overlayHide?.cancel() } else if !backgroundBusy { scheduleOverlayHide() }
        case "hide": overlay.orderOut(nil)
        case "show": showOverlay()
        case "activity":
            if let value = body["value"] as? [String: Any], let busy = value["busy"] as? Bool {
                if !interruptingSpeech { wake.suspend(busy) }
                if let delay = value["readingSeconds"] as? Double { overlayReadDelay = min(90,max(12,delay)) }
                if value["finished"] as? Bool == true { scheduleOverlayHide() }
            }
        case "voice-finished": finishManualVoice()
        default: break
        }
    }

    func callJS(_ method: String, _ argument: Any) {
        guard let data = try? JSONSerialization.data(withJSONObject: [argument]), let json = String(data: data, encoding: .utf8) else { return }
        web.evaluateJavaScript("window.jarvisNative?.\(method)(\(json).at(0))", completionHandler: nil)
    }

    @objc func recordShortcut() { showWindow(); web.evaluateJavaScript("window.jarvisNative?.toggleRecording()", completionHandler: nil) }
    @objc func openSettings() { showWindow(); web.evaluateJavaScript("window.jarvisNative?.settings()", completionHandler: nil) }
    @objc func showWindow() { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }

    func toggleRecording() {
        manualVoiceBusy = true
        wake.pauseForManual(true)
        if let active = recorder, active.isRecording {
            active.stop()
            callJS("recording", false)
            if let url = recordingURL, let audio = try? Data(contentsOf: url) {
                callJS("audio", audio.base64EncodedString())
                try? FileManager.default.removeItem(at: url)
            }
            recorder = nil; recordingURL = nil
            return
        }
        AVCaptureDevice.requestAccess(for: .audio) { [weak self] allowed in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if !allowed { self.finishManualVoice(); self.callJS("error", "Autorisez le microphone pour Jarvis dans Réglages Système → Confidentialité et sécurité → Microphone."); return }
                do {
                    let url = FileManager.default.temporaryDirectory.appendingPathComponent("jarvis-\(UUID().uuidString).wav")
                    let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16000.0, AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
                    let recorder = try AVAudioRecorder(url: url, settings: settings)
                    recorder.delegate = self
                    guard recorder.record(forDuration: 90) else { throw NSError(domain: "Jarvis", code: 1, userInfo: [NSLocalizedDescriptionKey: "Le microphone ne peut pas enregistrer."]) }
                    self.recorder = recorder; self.recordingURL = url
                    self.callJS("recording", true)
                } catch { self.finishManualVoice(); self.callJS("error", error.localizedDescription) }
            }
        }
    }

    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        if self.recorder?.isRecording == false && recordingURL != nil {
            callJS("recording", false)
            // Explicit stop already sends and clears the URL; automatic duration stop sends here.
            if let url = recordingURL, let audio = try? Data(contentsOf: url) {
                callJS("audio", audio.base64EncodedString()); try? FileManager.default.removeItem(at: url)
            }
            self.recorder = nil; recordingURL = nil
        }
    }

    func showError(_ text: String) {
        let alert = NSAlert(); alert.messageText = "Jarvis"; alert.informativeText = text; alert.runModal()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
    func applicationWillTerminate(_ notification: Notification) {
        wake.disable()
        recorder?.stop()
        if let url = recordingURL { try? FileManager.default.removeItem(at: url) }
        if let localMonitor = localMonitor { NSEvent.removeMonitor(localMonitor) }
        if let globalMonitor = globalMonitor { NSEvent.removeMonitor(globalMonitor) }
        if let server = server, server.isRunning { server.terminate() }
    }
}

@main struct JarvisMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = JarvisApp()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        withExtendedLifetime(delegate) { app.run() }
    }
}
