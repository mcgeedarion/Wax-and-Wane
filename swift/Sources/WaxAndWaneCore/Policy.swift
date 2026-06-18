import Foundation

func clampUnit(_ value: Float) -> Float { min(max(value, 0.0), 1.0) }

func normalizeAmbient(_ ambient: Float, dark: Float, bright: Float, gamma: Float) -> Float {
    let linear = clampUnit((ambient - dark) / (bright - dark))
    return pow(linear, gamma)
}

func mapAmbient(_ ambient: Float, minValue: Float, maxValue: Float, invert: Bool) -> Float {
    invert ? maxValue - ambient * (maxValue - minValue)
           : minValue + ambient * (maxValue - minValue)
}

struct RingBuffer {
    private var buf: [Float]
    private var index = 0
    private var count = 0
    private var total: Float = 0
    let capacity: Int

    init(capacity: Int) {
        precondition(capacity > 0, "RingBuffer capacity must be > 0")
        self.capacity = capacity
        self.buf = [Float](repeating: 0, count: capacity)
    }

    mutating func append(_ value: Float) {
        if count == capacity { total -= buf[index] } else { count += 1 }
        buf[index] = value
        total += value
        index = (index + 1) % capacity
    }

    var mean: Float { count > 0 ? total / Float(count) : 0 }
    var isEmpty: Bool { count == 0 }
}

func thresholdForDelta(_ delta: Float, changeThreshold: Float, riseThreshold: Float?, fallThreshold: Float?) -> Float {
    if delta > 0 { return riseThreshold ?? changeThreshold }
    if delta < 0 { return fallThreshold ?? changeThreshold }
    return changeThreshold
}

struct OutputChannelSettings {
    let control: BrightnessControl
    let minValue: Float
    let maxValue: Float
    let invert: Bool
    let manualValue: Float
}

func targetForControl(
    control: BrightnessControl,
    smoothedAmbient: Float,
    lastValue: Float,
    minValue: Float,
    maxValue: Float,
    invert: Bool,
    manualValue: Float,
    changeThreshold: Float,
    riseThreshold: Float? = nil,
    fallThreshold: Float? = nil
) -> Float? {
    targetForChannel(
        OutputChannelSettings(
            control: control,
            minValue: minValue,
            maxValue: maxValue,
            invert: invert,
            manualValue: manualValue
        ),
        smoothedAmbient: smoothedAmbient,
        lastValue: lastValue,
        changeThreshold: changeThreshold,
        riseThreshold: riseThreshold,
        fallThreshold: fallThreshold
    )
}

func targetForChannel(
    _ channel: OutputChannelSettings,
    smoothedAmbient: Float,
    lastValue: Float,
    changeThreshold: Float,
    riseThreshold: Float? = nil,
    fallThreshold: Float? = nil
) -> Float? {
    let target: Float
    switch channel.control {
    case .system:
        return nil
    case .manual:
        target = channel.manualValue
    case .auto:
        target = mapAmbient(smoothedAmbient, minValue: channel.minValue, maxValue: channel.maxValue, invert: channel.invert)
    }
    let delta = target - lastValue
    return abs(delta) > thresholdForDelta(delta, changeThreshold: changeThreshold, riseThreshold: riseThreshold, fallThreshold: fallThreshold) ? target : nil
}

func computeTargets(
    history: inout RingBuffer,
    ambientNow: Float,
    lastKeyboard: Float,
    lastScreen: Float,
    s: Settings
) -> (keyboard: Float?, screen: Float?) {
    history.append(ambientNow)
    let smoothedRaw = history.mean
    let calibrated = normalizeAmbient(smoothedRaw, dark: s.ambientDark, bright: s.ambientBright, gamma: s.outputGamma)

    let keyboard = OutputChannelSettings(
        control: s.keyboardControl,
        minValue: s.keyboardMin,
        maxValue: s.keyboardMax,
        invert: s.invertKeyboard,
        manualValue: s.manualKeyboardBrightness
    )
    let screen = OutputChannelSettings(
        control: s.screenControl,
        minValue: s.screenMin,
        maxValue: s.screenMax,
        invert: s.invertScreen,
        manualValue: s.manualScreenBrightness
    )

    return (
        targetForChannel(
            keyboard,
            smoothedAmbient: calibrated,
            lastValue: lastKeyboard,
            changeThreshold: s.changeThreshold,
            riseThreshold: s.riseThreshold,
            fallThreshold: s.fallThreshold
        ),
        targetForChannel(
            screen,
            smoothedAmbient: calibrated,
            lastValue: lastScreen,
            changeThreshold: s.changeThreshold,
            riseThreshold: s.riseThreshold,
            fallThreshold: s.fallThreshold
        )
    )
}
