import Foundation

#if canImport(AVFoundation)
import AVFoundation
import CoreMedia
import UserNotifications
import CoreVideo

func configureNotifications() {
    let center = UNUserNotificationCenter.current()
    center.requestAuthorization(options: [.alert, .sound]) { granted, error in
        if let error { fputs("Notification auth error: \(error.localizedDescription)\n", stderr) }
        if !granted { fputs("Notification access not granted; banners disabled.\n", stderr) }
    }
}

func postNotification(title: String, body: String) {
    let content = UNMutableNotificationContent()
    content.title = title
    content.body = body
    let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
    UNUserNotificationCenter.current().add(request, withCompletionHandler: nil)
}

final class RuntimeGuard {
    private let maxRuntime: TimeInterval
    private let reminderInterval: TimeInterval
    private let start = Date()
    private var lastReminder = Date()

    init(s: Settings) {
        maxRuntime = s.maxCameraRuntimeSeconds
        reminderInterval = s.reminderIntervalSeconds
    }

    var shouldExit: Bool { maxRuntime > 0 && Date().timeIntervalSince(start) >= maxRuntime }
    var remainingRuntime: TimeInterval { max(0, maxRuntime - Date().timeIntervalSince(start)) }

    func maybeRemind() {
        guard reminderInterval > 0, Date().timeIntervalSince(lastReminder) >= reminderInterval else { return }
        postNotification(title: "Wax and Wane", body: "Camera is active. Press Ctrl+C to stop.")
        lastReminder = Date()
    }
}

final class BrightnessSampler: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    private let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "com.waxandwane.camera", qos: .utility)
    private var _brightness: Float = 0.5
    private var lastProcessedFrameTime: TimeInterval = 0
    private let minimumFrameProcessingInterval: TimeInterval = 0.1
    private let lock = NSLock()

    var currentBrightness: Float {
        lock.lock(); defer { lock.unlock() }
        return _brightness
    }

    func start() throws {
        session.beginConfiguration()
        var configurationPending = true
        defer { if configurationPending { session.commitConfiguration() } }
        session.sessionPreset = .low

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .unspecified) else {
            throw NSError(domain: "WaxAndWane", code: 1, userInfo: [NSLocalizedDescriptionKey: "No camera found"])
        }
        let input = try AVCaptureDeviceInput(device: device)
        guard session.canAddInput(input) else {
            throw NSError(domain: "WaxAndWane", code: 2, userInfo: [NSLocalizedDescriptionKey: "Cannot add camera input"])
        }
        session.addInput(input)

        let output = AVCaptureVideoDataOutput()
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarFullRange]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: queue)
        guard session.canAddOutput(output) else {
            throw NSError(domain: "WaxAndWane", code: 3, userInfo: [NSLocalizedDescriptionKey: "Cannot add video output"])
        }
        session.addOutput(output)
        session.commitConfiguration()
        configurationPending = false

        print("Warming up camera auto-exposure (3 s)…")
        session.startRunning()
        Thread.sleep(forTimeInterval: 3.0)
        print("Ready.\n")
    }

    func stop() { if session.isRunning { session.stopRunning() } }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        let now = ProcessInfo.processInfo.systemUptime
        guard now - lastProcessedFrameTime >= minimumFrameProcessingInterval else { return }
        lastProcessedFrameTime = now
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        guard let lumaBase = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0) else { return }
        let height = CVPixelBufferGetHeightOfPlane(pixelBuffer, 0)
        let width = CVPixelBufferGetWidthOfPlane(pixelBuffer, 0)
        let stride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0)
        guard let normalizedMean = meanLuma(
            base: lumaBase.assumingMemoryBound(to: UInt8.self),
            width: width,
            height: height,
            bytesPerRow: stride
        ) else { return }
        lock.lock()
        _brightness = normalizedMean
        lock.unlock()
    }
}

func runDoctor() {
    print("Wax and Wane doctor")
    print("Platform: macOS")
    print("Safe executable directories: \(safePathEntries.joined(separator: ", "))")
    print("\nKeyboard backends:")
    keyboardCandidates().forEach { print("  \(backendDoctorLine($0))") }
    print("\nScreen backends:")
    screenCandidates().forEach { print("  \(backendDoctorLine($0))") }
    let cameraStatus = AVCaptureDevice.authorizationStatus(for: .video)
    print("\nCamera permission: \(cameraStatus)")
    let notificationCheck = DispatchSemaphore(value: 0)
    UNUserNotificationCenter.current().getNotificationSettings { settings in
        print("Notification permission: \(settings.authorizationStatus)")
        notificationCheck.signal()
    }
    if notificationCheck.wait(timeout: .now() + 2.0) == .timedOut {
        print("Notification permission: query timed out")
    }
}

func runApplication(settings: Settings) throws {
    try validateSettings(settings)
    let keyboardEnabled = settings.keyboardControl != .system
    let screenEnabled = settings.screenControl != .system
    let keyboardBackend = keyboardEnabled ? detectBackend(kind: .keyboard, preferredName: settings.keyboardBackend, dryRun: settings.dryRun) : nil
    let screenBackend = screenEnabled ? detectBackend(kind: .screen, preferredName: settings.screenBackend, dryRun: settings.dryRun) : nil
    let plan = try OutputPlan(settings: settings, keyboardAvailable: keyboardBackend != nil, screenAvailable: screenBackend != nil)
    if keyboardEnabled && keyboardBackend == nil {
        fputs("Warning: keyboard control unavailable; continuing with screen control only.\n", stderr)
    }
    if screenEnabled && screenBackend == nil {
        fputs("Warning: screen control unavailable; continuing with keyboard control only.\n", stderr)
    }

    let lifecycle = RuntimeLifecycle()
    let sigIntSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .global(qos: .userInitiated))
    let sigTermSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .global(qos: .userInitiated))
    let previousInt = signal(SIGINT, SIG_IGN)
    let previousTerm = signal(SIGTERM, SIG_IGN)
    sigIntSource.setEventHandler { lifecycle.requestStop() }
    sigTermSource.setEventHandler { lifecycle.requestStop() }
    sigIntSource.resume()
    sigTermSource.resume()
    defer {
        sigIntSource.cancel()
        sigTermSource.cancel()
        signal(SIGINT, previousInt)
        signal(SIGTERM, previousTerm)
    }

    let originalKeyboard = settings.restoreOriginalBrightness ? keyboardBackend?.currentBrightness() : nil
    let originalScreen = settings.restoreOriginalBrightness ? screenBackend?.currentBrightness() : nil
    var keyboardWritten = false
    var screenWritten = false
    var sampler: BrightnessSampler?
    defer {
        sampler?.stop()
        lifecycle.finish {
            if keyboardWritten { _ = keyboardBackend?.set(originalKeyboard ?? settings.defaultKeyboardBrightness) }
            if screenWritten { _ = screenBackend?.set(originalScreen ?? settings.defaultScreenBrightness) }
        }
    }

    if plan.needsCamera {
        if lifecycle.isStopping { return }
        configureNotifications()
        let semaphore = DispatchSemaphore(value: 0)
        AVCaptureDevice.requestAccess(for: .video) { _ in semaphore.signal() }
        while semaphore.wait(timeout: .now() + 0.1) == .timedOut {
            if lifecycle.isStopping { return }
        }
        if lifecycle.isStopping { return }
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            throw SettingsError.invalid("Camera access denied. Grant access in System Settings → Privacy & Security → Camera.")
        }
        let camera = BrightnessSampler()
        sampler = camera
        try camera.start()
        if lifecycle.isStopping { return }
        postNotification(title: "Wax and Wane", body: "Camera is now active to adjust brightness.")
    }

    var history = RingBuffer(capacity: settings.smoothingWindow)
    var lastKeyboard: Float = originalKeyboard ?? -1.0
    var lastScreen: Float = originalScreen ?? -1.0
    var lastWrite = Date.distantPast
    let runtimeGuard = RuntimeGuard(s: settings)
    print(plan.needsCamera ? "Ambient backlight running (camera active). Press Ctrl+C to stop." : "Manual brightness control running (camera off). Press Ctrl+C to stop.")
    if settings.dryRun { print("Dry-run mode: no brightness writes will be performed.") }

    while !lifecycle.isStopping {
        if runtimeGuard.shouldExit {
            print("Max runtime reached. Stopping.")
            lifecycle.requestStop()
            break
        }
        if plan.needsCamera { runtimeGuard.maybeRemind() }
        let ambientNow = sampler?.currentBrightness ?? 0.5
        let (newKbd, newScr) = computeTargets(history: &history, ambientNow: ambientNow, lastKeyboard: lastKeyboard, lastScreen: lastScreen, s: settings)
        let mayWrite = Date().timeIntervalSince(lastWrite) >= settings.minUpdateIntervalSeconds
        if mayWrite, let v = newKbd, let backend = keyboardBackend,
           lifecycle.write({ keyboardWritten = true; return backend.set(v) }) {
            lastKeyboard = v
            lastWrite = Date()
        }
        if mayWrite, let v = newScr, let backend = screenBackend,
           lifecycle.write({ screenWritten = true; return backend.set(v) }) {
            lastScreen = v
            lastWrite = Date()
        }
        let keyboardStatus = settings.keyboardControl == .system ? "system" : (keyboardBackend == nil ? "unavailable" : String(format: "%.0f%%", lastKeyboard * 100))
        let screenStatus = settings.screenControl == .system ? "system" : (screenBackend == nil ? "unavailable" : String(format: "%.0f%%", lastScreen * 100))
        if plan.needsCamera {
            let rawSmoothed = history.mean
            let calibrated = normalizeAmbient(rawSmoothed, dark: settings.ambientDark, bright: settings.ambientBright, gamma: settings.outputGamma)
            print(String(format: "Ambient raw %.3f calibrated %.3f → Keyboard %@ | Screen %@", rawSmoothed, calibrated, keyboardStatus, screenStatus))
        } else {
            print("Camera off → Keyboard \(keyboardStatus) | Screen \(screenStatus)")
        }
        let remaining = settings.maxCameraRuntimeSeconds > 0
            ? min(settings.pollIntervalSeconds, runtimeGuard.remainingRuntime)
            : settings.pollIntervalSeconds
        lifecycle.wait(seconds: remaining)
    }
    print("Restoring brightness…")
}

#else

func runDoctor() {
    print("Wax and Wane doctor")
    print("Platform: non-macOS (camera loop unavailable; policy tests and config tools are available)")
    print("Safe executable directories: \(safePathEntries.joined(separator: ", "))")
    print("\nKeyboard backends:")
    keyboardCandidates().forEach { print("  \(backendDoctorLine($0))") }
    print("\nScreen backends:")
    screenCandidates().forEach { print("  \(backendDoctorLine($0))") }
}

func runApplication(settings: Settings) throws {
    try validateSettings(settings)
    throw SettingsError.invalid("The camera brightness loop requires macOS AVFoundation; use 'doctor' or 'print-default-config' on this platform.")
}

#endif
