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
    configureNotifications()

    let keyboardEnabled = settings.keyboardControl != .system
    let screenEnabled = settings.screenControl != .system
    let keyboardBackend = keyboardEnabled ? detectBackend(kind: .keyboard, preferredName: settings.keyboardBackend, dryRun: settings.dryRun) : nil
    let screenBackend = screenEnabled ? detectBackend(kind: .screen, preferredName: settings.screenBackend, dryRun: settings.dryRun) : nil

    if !keyboardEnabled && !screenEnabled {
        fputs("Error: keyboard and screen are both set to system control; nothing to adjust.\n", stderr)
        exit(1)
    }
    if keyboardEnabled && keyboardBackend == nil && screenEnabled && screenBackend != nil {
        fputs("Warning: keyboard control unavailable; continuing with screen control only.\n", stderr)
    }
    if screenEnabled && screenBackend == nil && keyboardEnabled && keyboardBackend != nil {
        fputs("Warning: screen control unavailable; continuing with keyboard control only.\n", stderr)
    }
    if (keyboardEnabled && keyboardBackend == nil) && (screenEnabled && screenBackend == nil) {
        fputs("Error: no enabled output backends available. Install a backend or set that channel to system control.\n", stderr)
        exit(1)
    }

    let originalKeyboard = settings.restoreOriginalBrightness ? keyboardBackend?.currentBrightness() : nil
    let originalScreen = settings.restoreOriginalBrightness ? screenBackend?.currentBrightness() : nil

    let restoreLock = NSLock()
    var restored = false
    func restoreDefaults() {
        restoreLock.lock()
        guard !restored else { restoreLock.unlock(); return }
        restored = true
        restoreLock.unlock()
        if settings.keyboardControl != .system { _ = keyboardBackend?.set(originalKeyboard ?? settings.defaultKeyboardBrightness) }
        if settings.screenControl != .system { _ = screenBackend?.set(originalScreen ?? settings.defaultScreenBrightness) }
    }

    let semaphore = DispatchSemaphore(value: 0)
    AVCaptureDevice.requestAccess(for: .video) { granted in
        if !granted { fputs("Camera access denied.\nSystem Settings → Privacy & Security → Camera\n", stderr) }
        semaphore.signal()
    }
    semaphore.wait()
    guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else { exit(1) }

    let sampler = BrightnessSampler()
    do { try sampler.start() } catch {
        fputs("Camera error: \(error.localizedDescription)\n", stderr)
        exit(1)
    }

    postNotification(title: "Wax and Wane", body: "Camera is now active to adjust keyboard and screen brightness.")

    var history = RingBuffer(capacity: settings.smoothingWindow)
    var lastKeyboard: Float = originalKeyboard ?? -1.0
    var lastScreen: Float = originalScreen ?? -1.0
    var lastWrite = Date.distantPast
    let runtimeGuard = RuntimeGuard(s: settings)

    let sigIntSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .global(qos: .userInitiated))
    let sigTermSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .global(qos: .userInitiated))
    signal(SIGINT, SIG_IGN)
    signal(SIGTERM, SIG_IGN)
    let handleTermination: () -> Void = {
        print("\nRestoring brightness…")
        restoreDefaults()
        sampler.stop()
        exit(0)
    }
    sigIntSource.setEventHandler(handler: handleTermination)
    sigTermSource.setEventHandler(handler: handleTermination)
    sigIntSource.resume()
    sigTermSource.resume()

    print("Ambient backlight running (camera active). Press Ctrl+C to stop.\n")
    if settings.dryRun { print("Dry-run mode: no brightness writes will be performed.\n") }

    while true {
        if runtimeGuard.shouldExit {
            print("Max runtime reached. Stopping.")
            restoreDefaults()
            sampler.stop()
            break
        }
        runtimeGuard.maybeRemind()

        let ambientNow = sampler.currentBrightness
        let (newKbd, newScr) = computeTargets(history: &history, ambientNow: ambientNow, lastKeyboard: lastKeyboard, lastScreen: lastScreen, s: settings)
        let mayWrite = Date().timeIntervalSince(lastWrite) >= settings.minUpdateIntervalSeconds

        if mayWrite, let v = newKbd, let backend = keyboardBackend, backend.set(v) {
            lastKeyboard = v
            lastWrite = Date()
        }
        if mayWrite, let v = newScr, let backend = screenBackend, backend.set(v) {
            lastScreen = v
            lastWrite = Date()
        }

        let rawSmoothed = history.isEmpty ? ambientNow : history.mean
        let calibrated = normalizeAmbient(rawSmoothed, dark: settings.ambientDark, bright: settings.ambientBright, gamma: settings.outputGamma)
        let keyboardStatus = settings.keyboardControl == .system ? "system" : (keyboardBackend == nil ? "unavailable" : String(format: "%.0f%%", lastKeyboard * 100))
        let screenStatus = settings.screenControl == .system ? "system" : (screenBackend == nil ? "unavailable" : String(format: "%.0f%%", lastScreen * 100))
        print(String(format: "Ambient raw %.3f calibrated %.3f → Keyboard %@ | Screen %@", rawSmoothed, calibrated, keyboardStatus, screenStatus))
        Thread.sleep(forTimeInterval: settings.pollIntervalSeconds)
    }
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
