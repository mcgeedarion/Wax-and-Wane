import Foundation

struct OutputPlan {
    let needsCamera: Bool

    init(settings: Settings, keyboardAvailable: Bool, screenAvailable: Bool) throws {
        let keyboardEnabled = settings.keyboardControl != .system
        let screenEnabled = settings.screenControl != .system
        guard keyboardEnabled || screenEnabled else {
            throw SettingsError.invalid("Keyboard and screen are both set to system control; nothing to adjust.")
        }
        let keyboardUsable = keyboardEnabled && keyboardAvailable
        let screenUsable = screenEnabled && screenAvailable
        guard keyboardUsable || screenUsable else {
            throw SettingsError.invalid("No enabled output backends available. Install a backend or enable an available channel.")
        }
        needsCamera = (keyboardUsable && settings.keyboardControl == .auto)
            || (screenUsable && settings.screenControl == .auto)
    }
}

// All writes and restoration share one gate. Signal handlers only request a stop.
final class RuntimeLifecycle {
    private let condition = NSCondition()
    private var stopping = false
    private var finished = false

    var isStopping: Bool {
        condition.lock(); defer { condition.unlock() }
        return stopping
    }

    func requestStop() {
        condition.lock(); defer { condition.unlock() }
        stopping = true
        condition.broadcast()
    }

    @discardableResult
    func write(_ action: () -> Bool) -> Bool {
        condition.lock(); defer { condition.unlock() }
        guard !stopping else { return false }
        return action()
    }

    func finish(restoring action: () -> Void) {
        condition.lock(); defer { condition.unlock() }
        guard !finished else { return }
        stopping = true
        finished = true
        condition.broadcast()
        action()
    }

    func wait(seconds: TimeInterval) {
        condition.lock(); defer { condition.unlock() }
        let deadline = Date().addingTimeInterval(seconds)
        while !stopping {
            if !condition.wait(until: deadline) { break }
        }
    }
}
