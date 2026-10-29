import Cocoa
import WebKit
import QuartzCore

/// Native layers keep animating when WebKit's background page is throttled.
final class VoiceIndicator: NSView {
    private let ring = CAShapeLayer()
    private var bars: [CALayer] = []
    private var phase = ""

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        layer?.cornerRadius = 16
        ring.path = CGPath(ellipseIn: CGRect(x: 2, y: 2, width: 28, height: 28), transform: nil)
        ring.fillColor = NSColor.clear.cgColor
        ring.lineWidth = 1
        ring.isHidden = true
        layer?.addSublayer(ring)
        for i in 0..<5 {
            let bar = CALayer()
            bar.frame = CGRect(x: 7 + i*4, y: 9, width: 2, height: 14)
            bar.cornerRadius = 1
            layer?.addSublayer(bar)
            bars.append(bar)
        }
        setPhase("idle")
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    func setPhase(_ value: String) {
        guard value != phase else { return }
        phase = value
        let color = value == "working" ? NSColor(calibratedRed: 0.86, green: 0.77, blue: 0.60, alpha: 1) : NSColor(calibratedRed: 0.68, green: 0.87, blue: 0.84, alpha: 1)
        ring.strokeColor = color.cgColor
        ring.removeAllAnimations()
        for (i, bar) in bars.enumerated() {
            bar.backgroundColor = color.cgColor
            bar.removeAllAnimations()
            if value != "idle" && value != "listening" && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
                let wave = CABasicAnimation(keyPath: "transform.scale.y")
                wave.fromValue = 0.2; wave.toValue = 0.65 + Double(i % 3)*0.18
                wave.duration = 0.3 + Double(i)*0.09
                wave.autoreverses = true; wave.repeatCount = .infinity
                wave.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                bar.add(wave, forKey: "wave")
            }
        }
        if value != "idle" && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            let pulse = CABasicAnimation(keyPath: "opacity")
            pulse.fromValue = 0.25; pulse.toValue = 1; pulse.duration = 0.65
            pulse.autoreverses = true; pulse.repeatCount = .infinity
            ring.add(pulse, forKey: "pulse")
        }
    }

    func setLevel(_ value: Double) {
        guard phase == "listening" else { return }
        CATransaction.begin(); CATransaction.setDisableActions(true)
        for (i, bar) in bars.enumerated() {
            let amplitude = max(0.15, min(1, value * (1.1 + Double(i % 3) * 0.2)))
            bar.transform = CATransform3DMakeScale(1, amplitude, 1)
        }
        CATransaction.commit()
    }
}

extension JarvisApp {
    func monitorActivity() {
        guard let token = try? String(contentsOf: project.appendingPathComponent(".state/token"), encoding: .utf8) else { return }
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8766/api/activity")!)
        request.setValue("Bearer " + token.trimmingCharacters(in: .whitespacesAndNewlines), forHTTPHeaderField: "Authorization")
        URLSession.shared.dataTask(with: request) { [weak self] data, response, _ in
            guard let data = data, let info = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
            DispatchQueue.main.async {
                guard let self = self else { return }
                let running = info["status"] as? String == "running"
                let busy = running || info["speaking"] as? Bool == true
                if busy { self.voiceIndicator.setPhase(info["speaking"] as? Bool == true ? "speaking" : "working") }
                if let id = info["id"] as? String, id != self.lastBackgroundTask {
                    self.lastBackgroundTask = id
                    if busy { self.showOverlay() }
                }
                // Reconcile even if a short task finished between polls: submitting
                // a wake command suspends recognition before the task is observed.
                if !self.interruptingSpeech { self.wake.suspend(busy) }
                if self.backgroundBusy != busy {
                    self.backgroundBusy = busy
                    if !busy { self.voiceIndicator.setPhase("idle"); self.scheduleOverlayHide() }
                }
            }
        }.resume()
    }

    func makeOverlay() {
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.add(self, name: "jarvis")
        configuration.userContentController.addUserScript(WKUserScript(source: "document.body.classList.add('native-shell')", injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        overlayWeb = WKWebView(frame: .zero, configuration: configuration)
        overlayWeb.navigationDelegate = self
        overlayWeb.setValue(false, forKey: "drawsBackground")
        overlayWeb.wantsLayer = true
        overlayWeb.layer?.cornerRadius = 24
        overlayWeb.layer?.masksToBounds = true
        overlay = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 360, height: 142), styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        overlay.isFloatingPanel = true
        overlay.hidesOnDeactivate = false
        overlay.level = NSWindow.Level(rawValue: NSWindow.Level.statusBar.rawValue + 1)
        overlay.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        overlay.isOpaque = false
        overlay.backgroundColor = .clear
        overlay.hasShadow = true
        overlay.appearance = NSAppearance(named: .darkAqua)
        let container = NSView(frame: NSRect(x: 0, y: 0, width: 360, height: 142))
        container.wantsLayer = true
        container.layer?.cornerRadius = 24
        container.layer?.masksToBounds = true
        let glass = NSVisualEffectView(frame: container.bounds)
        glass.material = .hudWindow
        glass.blendingMode = .behindWindow
        glass.state = .active
        glass.wantsLayer = true
        glass.layer?.cornerRadius = 24
        glass.layer?.masksToBounds = true
        glass.alphaValue = NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency ? 1 : 0.72
        glass.autoresizingMask = [.width,.height]
        container.addSubview(glass)
        overlayWeb.frame = container.bounds
        overlayWeb.autoresizingMask = [.width, .height]
        container.addSubview(overlayWeb)
        voiceIndicator.frame = NSRect(x:17,y:container.bounds.height-49,width:32,height:32)
        voiceIndicator.autoresizingMask = [.minXMargin,.maxXMargin,.minYMargin]
        container.addSubview(voiceIndicator)
        overlay.contentView = container
        overlayScreenObserver = NotificationCenter.default.addObserver(forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main) { [weak self] _ in
            guard let self = self else { return }
            self.configureNotch()
            self.resizeOverlay(height: self.overlay.frame.height, width: self.overlay.frame.width)
        }
        configureNotch()
    }

    func notchScreen() -> NSScreen? {
        NSScreen.screens.first(where: { $0.safeAreaInsets.top > 0 }) ?? NSScreen.main ?? NSScreen.screens.first
    }

    func configureNotch() {
        guard let screen = notchScreen() else { return }
        let hasNotch = screen.safeAreaInsets.top > 0
        let left = screen.auxiliaryTopLeftArea, right = screen.auxiliaryTopRightArea
        overlayNotchWidth = hasNotch ? max(0, (right?.minX ?? screen.frame.midX + 90) - (left?.maxX ?? screen.frame.midX - 90)) : 100
        overlayNotchHeight = hasNotch ? max(32, screen.safeAreaInsets.top) : 32
        for view in [overlay.contentView, overlayWeb, overlay.contentView?.subviews.first] {
            view?.layer?.maskedCorners = hasNotch ? [.layerMinXMinYCorner,.layerMaxXMinYCorner] : [.layerMinXMinYCorner,.layerMaxXMinYCorner,.layerMinXMaxYCorner,.layerMaxXMaxYCorner]
        }
        let payload: [String: Any] = ["hasNotch":hasNotch,"notchWidth":overlayNotchWidth,"notchHeight":overlayNotchHeight,"availableWidth":min(480,screen.frame.width-24),"responseCap":max(100,min(420,screen.frame.height*0.5)-overlayNotchHeight-85)]
        if let data = try? JSONSerialization.data(withJSONObject: payload), let json = String(data:data,encoding:.utf8) {
            overlayWeb.evaluateJavaScript("window.jarvisOverlay?.configure(\(json))",completionHandler:nil)
            try? data.write(to:project.appendingPathComponent(".state/overlay-layout.json"),options:.atomic)
        }
        layoutVoiceIndicator()
    }

    func overlayFrame(width: CGFloat, height: CGFloat) -> NSRect {
        guard let screen = notchScreen() else { return NSRect(x:0,y:0,width:width,height:height) }
        let left = screen.auxiliaryTopLeftArea, right = screen.auxiliaryTopRightArea
        let center = screen.safeAreaInsets.top > 0 ? ((left?.maxX ?? screen.frame.midX) + (right?.minX ?? screen.frame.midX))/2 : screen.frame.midX
        let top = screen.safeAreaInsets.top > 0 ? screen.frame.maxY : screen.visibleFrame.maxY - 8
        return NSRect(x:center-width/2,y:top-height,width:width,height:height)
    }

    func layoutVoiceIndicator() {
        voiceIndicator.frame = NSRect(x:overlay.frame.width/2 + overlayNotchWidth/2 + 3,y:overlay.frame.height-overlayNotchHeight/2-16,width:32,height:32)
    }

    func showOverlay() {
        overlayHide?.cancel()
        overlayVisibilityEpoch += 1
        overlay.alphaValue = 1
        // Login launch uses `open -j`: ordering a window alone does not unhide
        // an accessory application. Reveal only its panel without taking focus.
        NSApp.unhideWithoutActivation()
        configureNotch()
        overlay.setFrame(overlayFrame(width:overlay.frame.width,height:overlay.frame.height),display:true)
        layoutVoiceIndicator()
        let entering = !overlay.isVisible
        if entering { overlay.alphaValue = 0 }
        overlay.orderFrontRegardless()
        if entering { NSAnimationContext.runAnimationGroup { context in
            context.duration = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion ? 0 : 0.18
            overlay.animator().alphaValue = 1
        } }
    }

    func resizeOverlay(height: Double, width: Double? = nil) {
        let screen = notchScreen()
        let cap = min(440, (screen?.frame.height ?? 800)*0.55)
        let targetHeight = CGFloat(min(cap,max(105,height)))
        let targetWidth = CGFloat(min(min(480,(screen?.frame.width ?? 800)-24),max(overlayNotchWidth+176,width ?? overlay.frame.width)))
        let frame = overlayFrame(width:targetWidth,height:targetHeight)
        guard abs(overlay.frame.height-targetHeight)>1 || abs(overlay.frame.width-targetWidth)>1 || abs(overlay.frame.origin.x-frame.origin.x)>1 else { return }
        NSAnimationContext.runAnimationGroup { context in
            context.duration = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion ? 0 : 0.24
            context.timingFunction = CAMediaTimingFunction(name:.easeInEaseOut)
            overlay.animator().setFrame(frame,display:true)
        } completionHandler: { [weak self] in
            self?.layoutVoiceIndicator()
        }
    }

    func scheduleOverlayHide() {
        overlayHide?.cancel()
        guard !overlayHeld else { return }
        let epoch = overlayVisibilityEpoch
        let work = DispatchWorkItem { [weak self] in
            guard let self = self else { return }
            NSAnimationContext.runAnimationGroup { context in
                context.duration = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion ? 0 : 0.16
                self.overlay.animator().alphaValue = 0
            } completionHandler: { [weak self] in
                guard let self = self, self.overlayVisibilityEpoch == epoch, !self.backgroundBusy, !self.overlayHeld else { return }
                self.overlay.orderOut(nil); self.overlay.alphaValue = 1
            }
        }
        overlayHide = work
        DispatchQueue.main.asyncAfter(deadline: .now() + overlayReadDelay, execute: work)
    }

    func overlayJS(_ method: String, _ text: String? = nil) {
        let argument: String
        if let text = text, let data = try? JSONSerialization.data(withJSONObject: [text]), let json = String(data: data, encoding: .utf8) { argument = json + ".at(0)" }
        else { argument = "" }
        overlayWeb.evaluateJavaScript("window.jarvisOverlay?.\(method)(\(argument))", completionHandler: nil)
    }

    func configureWake() {
        if let data = try? Data(contentsOf: project.appendingPathComponent(".state/app-vocabulary.json")), let names = try? JSONDecoder().decode([String].self, from: data) { wake.vocabulary = names }
        wake.onWake = { [weak self] in self?.voiceIndicator.setPhase("listening"); self?.showOverlay(); self?.overlayJS("listening") }
        wake.onIdle = { [weak self] in self?.voiceIndicator.setPhase("idle"); self?.overlayJS("idle"); self?.overlay.orderOut(nil) }
        wake.onLevel = { [weak self] level in self?.voiceIndicator.setLevel(level); self?.overlayWeb.evaluateJavaScript("window.jarvisOverlay?.level(\(level))", completionHandler: nil) }
        wake.onCommand = { [weak self] text in self?.submitVoiceCommand(text) }
        wake.onCommandAudio = { [weak self] text, audio in self?.submitVoiceCommand(text, audio: audio) }
        wake.onPartialCommand = { [weak self] text in self?.overlayJS("transcript", text) }
        wake.onTurnCheck = { [weak self] audio, completion in
            guard let self = self,
                  let token = try? String(contentsOf: self.project.appendingPathComponent(".state/token"), encoding: .utf8) else { completion(nil); return }
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8766/api/voice/turn")!)
            request.httpMethod = "POST"; request.timeoutInterval = 0.6
            request.setValue("Bearer " + token.trimmingCharacters(in: .whitespacesAndNewlines), forHTTPHeaderField: "Authorization")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: ["audio":audio.base64EncodedString()])
            URLSession.shared.dataTask(with: request) { data, response, _ in
                let info = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String:Any] }
                let complete = (response as? HTTPURLResponse)?.statusCode == 200 ? info?["complete"] as? Bool : nil
                DispatchQueue.main.async { completion(complete) }
            }.resume()
        }
        wake.onInterrupt = { [weak self] in self?.interruptVoice() }
        wake.onStatus = { [weak self] text in
            guard let self = self else { return }
            self.statusItem.button?.toolTip = "Jarvis · " + text
            let info: [String: Any] = ["enabled": self.listeningEnabled, "status": text, "updated": ISO8601DateFormatter().string(from: Date())]
            if let data = try? JSONSerialization.data(withJSONObject: info) { try? data.write(to: self.project.appendingPathComponent(".state/wake-status.json"), options: .atomic) }
        }
    }

    func finishManualVoice() {
        manualVoiceBusy = false
        wake.pauseForManual(false)
        wake.suspend(backgroundBusy)
    }

    func interruptVoice() {
        guard let token = try? String(contentsOf: project.appendingPathComponent(".state/token"), encoding: .utf8) else { return }
        interruptingSpeech = true
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8766/api/cancel")!)
        request.httpMethod = "POST"
        request.setValue("Bearer " + token.trimmingCharacters(in: .whitespacesAndNewlines), forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 12
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.interruptingSpeech = false
                let pending = self.pendingVoiceCommand
                self.pendingVoiceCommand = nil
                if (response as? HTTPURLResponse)?.statusCode == 200 {
                    self.backgroundBusy = false
                    self.wake.suspend(false)
                    if let (text, audio) = pending { self.submitVoiceCommand(text, audio:audio) }
                } else {
                    self.overlayJS("error", "Je n’ai pas pu confirmer l’arrêt de la tâche.")
                    self.wake.suspend(self.backgroundBusy)
                }
            }
        }.resume()
    }

    @objc func toggleVoice() {
        listeningEnabled.toggle()
        UserDefaults.standard.set(listeningEnabled, forKey: "voiceEnabled")
        voiceMenuItem.state = listeningEnabled ? .on : .off
        if listeningEnabled { wake.enable() } else { wake.disable() }
    }

    func submitVoiceCommand(_ text: String, audio: Data? = nil) {
        if interruptingSpeech { pendingVoiceCommand = (text,audio); return }
        guard let token = try? String(contentsOf: project.appendingPathComponent(".state/token"), encoding: .utf8) else { return }
        wake.suspend(true)
        overlayJS("thinking", text)
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8766/api/voice-command")!)
        request.httpMethod = "POST"
        request.setValue("Bearer " + token.trimmingCharacters(in: .whitespacesAndNewlines), forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var payload: [String: Any] = ["text": text]
        if let audio = audio { payload["audio"] = audio.base64EncodedString() }
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if let response = response as? HTTPURLResponse, response.statusCode == 200 { return }
                var detail = error?.localizedDescription ?? "La demande n’a pas pu démarrer."
                if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let value = json["detail"] as? String { detail = value }
                self.overlayJS("error", detail)
                self.wake.suspend(false)
                self.scheduleOverlayHide()
            }
        }.resume()
    }
}
