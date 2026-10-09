import AppKit
import WebKit

// Borderless windows need to opt into keyboard focus and the responder chain.
final class ForgeWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

// A native window owns both the WebKit view and its private local backend.
final class AudioForgeApp: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var backend: Process?
    private var backendURL: URL?
    private var serverToken = ""
    private var buffer = Data()
    private var stopping = false
    private var ready = false
    private var queuedFiles: [String] = []
    private var locale = UserDefaults.standard.string(forKey: "AudioForgeLanguage") ?? "en"
    private var startupTimer: Timer?
    private var titleDragMonitor: Any?
    private var restoreFrame: NSRect?

    private func text(_ key: String) -> String {
        let en = ["quit":"Quit Audio Forge", "about":"About Audio Forge", "file":"File", "open":"Open File…", "edit":"Edit", "undo":"Undo", "redo":"Redo", "cut":"Cut", "copy":"Copy", "paste":"Paste", "select":"Select All", "window":"Window", "minimize":"Minimize", "zoom":"Zoom", "help":"Help", "startup":"Audio Forge could not start", "busy":"Conversion in progress", "wait":"Please wait for the conversion to finish before quitting.", "ok":"OK"]
        let zh = ["quit":"退出 Audio Forge", "about":"关于 Audio Forge", "file":"文件", "open":"打开文件…", "edit":"编辑", "undo":"撤销", "redo":"重做", "cut":"剪切", "copy":"复制", "paste":"粘贴", "select":"全选", "window":"窗口", "minimize":"最小化", "zoom":"缩放", "help":"帮助", "startup":"Audio Forge 无法启动", "busy":"正在转换", "wait":"请等待转换完成后再退出。", "ok":"确定"]
        let ja = ["quit":"Audio Forge を終了", "about":"Audio Forge について", "file":"ファイル", "open":"ファイルを開く…", "edit":"編集", "undo":"取り消す", "redo":"やり直す", "cut":"カット", "copy":"コピー", "paste":"ペースト", "select":"すべてを選択", "window":"ウィンドウ", "minimize":"最小化", "zoom":"拡大／縮小", "help":"ヘルプ", "startup":"Audio Forge を起動できません", "busy":"変換中です", "wait":"変換が完了してから終了してください。", "ok":"OK"]
        return (locale == "zh-CN" ? zh : locale == "ja" ? ja : en)[key] ?? en[key] ?? key
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        if !["en", "zh-CN", "ja"].contains(locale) { locale = "en" }
        installMenu()
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.add(self, name: "desktop")
        // Language preferences persist across the backend's random localhost ports.
        let preference = "try { localStorage.setItem('audio-forge-language', \(jsonString(locale))); } catch (_) {}"
        configuration.userContentController.addUserScript(WKUserScript(source: preference, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        window = ForgeWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 680), styleMask: [.borderless, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Audio Forge"
        window.minSize = NSSize(width: 680, height: 580)
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.contentView = webView
        window.hasShadow = true
        // Only the HTML title bar moves the window; fields and caption buttons
        // keep their ordinary WebKit mouse behavior. Coordinates are in points.
        titleDragMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDown) { [weak self] event in
            guard let self = self, event.window === self.window else { return event }
            let fromTop = self.window.frame.height - event.locationInWindow.y
            let x = event.locationInWindow.x
            if fromTop >= 3 && fromTop <= 27 && x >= 3 && x < self.window.frame.width - 70 {
                if event.clickCount == 2 { self.toggleWindowZoom() }
                else { self.window.performDrag(with: event) }
                return nil
            }
            return event
        }
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startBackend()
    }

    private func item(_ title: String, _ action: Selector?, _ key: String = "", target: AnyObject? = nil) -> NSMenuItem {
        let result = NSMenuItem(title: title, action: action, keyEquivalent: key)
        result.target = target
        return result
    }
    private func installMenu() {
        let bar = NSMenu()
        let app = NSMenuItem(title: "Audio Forge", action: nil, keyEquivalent: "")
        let appMenu = NSMenu(title: "Audio Forge")
        appMenu.addItem(item(text("about"), #selector(showAbout), target: self))
        appMenu.addItem(.separator())
        appMenu.addItem(item(text("quit"), #selector(NSApplication.terminate(_:)), "q", target: NSApp))
        app.submenu = appMenu; bar.addItem(app)
        let file = NSMenuItem(title: text("file"), action: nil, keyEquivalent: "")
        let fileMenu = NSMenu(title: text("file"))
        fileMenu.addItem(item(text("open"), #selector(openFile), "o", target: self))
        file.submenu = fileMenu; bar.addItem(file)
        let edit = NSMenuItem(title: text("edit"), action: nil, keyEquivalent: "")
        let editMenu = NSMenu(title: text("edit"))
        editMenu.addItem(item(text("undo"), Selector(("undo:")), "z"))
        let redo = item(text("redo"), Selector(("redo:")), "z"); redo.keyEquivalentModifierMask = [.command, .shift]; editMenu.addItem(redo)
        editMenu.addItem(.separator())
        editMenu.addItem(item(text("cut"), #selector(NSText.cut(_:)), "x"))
        editMenu.addItem(item(text("copy"), #selector(NSText.copy(_:)), "c"))
        editMenu.addItem(item(text("paste"), #selector(NSText.paste(_:)), "v"))
        editMenu.addItem(item(text("select"), #selector(NSText.selectAll(_:)), "a"))
        edit.submenu = editMenu; bar.addItem(edit)
        let win = NSMenuItem(title: text("window"), action: nil, keyEquivalent: "")
        let winMenu = NSMenu(title: text("window"))
        winMenu.addItem(item(text("minimize"), #selector(NSWindow.performMiniaturize(_:)), "m"))
        winMenu.addItem(item(text("zoom"), #selector(toggleWindowZoom), target: self))
        win.submenu = winMenu; bar.addItem(win); NSApp.windowsMenu = winMenu
        let help = NSMenuItem(title: text("help"), action: nil, keyEquivalent: "")
        let helpMenu = NSMenu(title: text("help")); helpMenu.addItem(item(text("about"), #selector(showAbout), target: self))
        help.submenu = helpMenu; bar.addItem(help)
        NSApp.mainMenu = bar
    }

    @objc private func showAbout() { if ready { webView.evaluateJavaScript("document.getElementById('aboutModal').showModal()", completionHandler: nil) } }
    @objc private func openFile() { if ready { webView.evaluateJavaScript("document.getElementById('chooseInput').click()", completionHandler: nil) } }

    @objc private func toggleWindowZoom() {
        if let original = restoreFrame {
            restoreFrame = nil
            window.setFrame(original, display: true)
        } else if let screen = window.screen ?? NSScreen.main {
            restoreFrame = window.frame
            window.setFrame(screen.visibleFrame, display: true)
        }
        syncWindowState()
    }
    private func syncWindowState() {
        if ready { webView.evaluateJavaScript("window.audioForgeWindowState(\(restoreFrame != nil ? "true" : "false"))", completionHandler: nil) }
    }

    private func startBackend() {
        guard let resources = Bundle.main.resourceURL else { fail("Missing application resources."); return }
        let runtime = resources.appendingPathComponent("runtime")
        let scripts = resources.appendingPathComponent("backend")
        let child = Process()
        child.executableURL = runtime.appendingPathComponent("bin/python3")
        child.arguments = ["-B", "-s", "-S", "-u", scripts.appendingPathComponent("m4a_gui.py").path, "--desktop", "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)]
        var environment = ProcessInfo.processInfo.environment.filter { !$0.key.hasPrefix("PYTHON") && !$0.key.hasPrefix("DYLD_") && $0.key != "__PYVENV_LAUNCHER__" }
        environment["PYTHONHOME"] = runtime.path
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PATH"] = runtime.appendingPathComponent("bin").path + ":/usr/bin:/bin:/usr/sbin:/sbin"
        environment["AUDIO_FORGE_DESKTOP"] = "1"
        child.environment = environment
        child.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
        let output = Pipe(); child.standardOutput = output
        let errors = Pipe(); child.standardError = errors
        // Drain diagnostics so a large FFmpeg failure cannot block the subprocess.
        errors.fileHandleForReading.readabilityHandler = { handle in _ = handle.availableData }
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if !data.isEmpty { DispatchQueue.main.async { self?.receive(data) } }
        }
        child.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self = self, !self.stopping else { return }
                self.startupTimer?.invalidate()
                if self.ready && process.terminationStatus == 0 { NSApp.terminate(nil) }
                else { self.fail("The local audio service stopped (exit \(process.terminationStatus)).") }
            }
        }
        backend = child
        do {
            try child.run()
            startupTimer = Timer.scheduledTimer(withTimeInterval: 25, repeats: false) { [weak self] _ in
                guard let self = self, self.backendURL == nil else { return }
                self.fail("The local audio service did not start in time.")
            }
        } catch { fail(error.localizedDescription) }
    }

    private func receive(_ data: Data) {
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 10) {
            let line = buffer.subdata(in: 0..<newline); buffer.removeSubrange(0...newline)
            guard backendURL == nil, let object = try? JSONSerialization.jsonObject(with: line) as? [String: Any], object["event"] as? String == "ready", let value = object["url"] as? String, let url = URL(string: value), url.host == "127.0.0.1", url.scheme == "http", let token = object["token"] as? String else { continue }
            backendURL = url; serverToken = token; startupTimer?.invalidate()
            webView.load(URLRequest(url: url))
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard let url = webView.url, isLocal(url) else { return }
        ready = true
        syncWindowState()
        if let file = queuedFiles.first { queuedFiles.removeAll(); openMedia(file) }
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { if !stopping { fail(error.localizedDescription) } }
    private func isLocal(_ url: URL) -> Bool { url.scheme == "http" && url.host == "127.0.0.1" && url.port == backendURL?.port }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        decisionHandler(navigationAction.request.url.map(isLocal) == true ? .allow : .cancel)
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, let origin = message.frameInfo.request.url, isLocal(origin), let payload = message.body as? [String: String], let action = payload["action"] else { return }
        switch action {
        case "minimize": window.miniaturize(nil)
        case "maximize": toggleWindowZoom()
        case "quit": NSApp.terminate(nil)
        case "language":
            if let value = payload["value"], ["en", "zh-CN", "ja"].contains(value) {
                locale = value; UserDefaults.standard.set(value, forKey: "AudioForgeLanguage"); installMenu()
            }
        default: break
        }
    }

    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        if let file = filenames.first { if ready { openMedia(file) } else { queuedFiles = [file] } }
        sender.reply(toOpenOrPrint: .success)
    }
    private func jsonString(_ value: String) -> String {
        let encoded = try! JSONSerialization.data(withJSONObject: [value])
        let string = String(data: encoded, encoding: .utf8)!
        return String(string.dropFirst().dropLast())
    }
    private func openMedia(_ path: String) { webView.evaluateJavaScript("window.audioForgeOpenFile(\(jsonString(path)))", completionHandler: nil) }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { window.deminiaturize(nil); window.makeKeyAndOrderFront(nil); return true }
    func windowShouldClose(_ sender: NSWindow) -> Bool { NSApp.terminate(nil); return false }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if stopping || backend?.isRunning != true { return .terminateNow }
        guard let base = backendURL else { return .terminateNow }
        var request = URLRequest(url: base.appendingPathComponent("api/status")); request.setValue(serverToken, forHTTPHeaderField: "X-M4A-Token"); request.timeoutInterval = 4
        URLSession.shared.dataTask(with: request) { [weak self] data, _, _ in
            DispatchQueue.main.async {
                guard let self = self else { sender.reply(toApplicationShouldTerminate: true); return }
                let job = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
                if job?["state"] as? String == "running" {
                    let alert = NSAlert(); alert.messageText = self.text("busy"); alert.informativeText = self.text("wait"); alert.addButton(withTitle: self.text("ok")); alert.runModal()
                    sender.reply(toApplicationShouldTerminate: false)
                } else if job == nil && self.backend?.isRunning == true {
                    // A disconnected page may still have a conversion in progress.
                    let alert = NSAlert(); alert.messageText = self.text("busy"); alert.informativeText = self.text("wait"); alert.addButton(withTitle: self.text("ok")); alert.runModal()
                    sender.reply(toApplicationShouldTerminate: false)
                } else {
                    self.stopping = true
                    sender.reply(toApplicationShouldTerminate: true)
                }
            }
        }.resume()
        return .terminateLater
    }
    func applicationWillTerminate(_ notification: Notification) {
        stopping = true; startupTimer?.invalidate()
        if let monitor = titleDragMonitor { NSEvent.removeMonitor(monitor) }
        if backend?.isRunning == true { backend?.terminate(); backend?.waitUntilExit() }
    }
    private func fail(_ detail: String) {
        if stopping { return }
        stopping = true
        let alert = NSAlert(); alert.messageText = text("startup"); alert.informativeText = detail; alert.addButton(withTitle: text("ok")); alert.runModal()
        NSApp.terminate(nil)
    }
}

let application = NSApplication.shared
let delegate = AudioForgeApp()
application.setActivationPolicy(.regular)
application.delegate = delegate
application.run()
