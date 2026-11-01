import Foundation
import XCTest
@testable import WaxAndWaneCore

final class RuntimeRegressionTests: XCTestCase {
    func testOutputPlanCoversEveryModeAndAvailabilityCombination() throws {
        let modes: [BrightnessControl] = [.system, .manual, .auto]
        for keyboard in modes {
            for screen in modes {
                for keyboardAvailable in [false, true] {
                    for screenAvailable in [false, true] {
                        var settings = Settings()
                        settings.keyboardControl = keyboard
                        settings.screenControl = screen
                        let hasKeyboard = keyboard != .system && keyboardAvailable
                        let hasScreen = screen != .system && screenAvailable
                        if !hasKeyboard && !hasScreen {
                            XCTAssertThrowsError(try OutputPlan(settings: settings, keyboardAvailable: keyboardAvailable, screenAvailable: screenAvailable))
                        } else {
                            let plan = try OutputPlan(settings: settings, keyboardAvailable: keyboardAvailable, screenAvailable: screenAvailable)
                            XCTAssertEqual(plan.needsCamera, (hasKeyboard && keyboard == .auto) || (hasScreen && screen == .auto))
                        }
                    }
                }
            }
        }
    }

    func testKeyboardHelpersUseNormalizedArguments() {
        for candidate in keyboardCandidates() {
            for value in [Float(0), 0.5, 0.75, 1] {
                XCTAssertEqual(candidate.builder(value), [String(format: "%.3f", value)])
            }
        }
    }

    func testHomebrewSymlinkAndDirectHelperResolve() throws {
        try withHelperFixture { root, bin, cellar, helper in
            XCTAssertEqual(resolveExecutable("helper", searchPaths: [bin.path], targetRoots: [bin.path, cellar.path]), helper.path)
            let direct = bin.appendingPathComponent("direct")
            try makeExecutable(direct)
            XCTAssertEqual(resolveExecutable("direct", searchPaths: [bin.path], targetRoots: [bin.path]), direct.path)
            XCTAssertNil(resolveExecutable("../direct", searchPaths: [root.path], targetRoots: [root.path]))
        }
    }

    func testHelperOutsideAllowedRootsIsRejected() throws {
        try withHelperFixture { root, bin, _, _ in
            let outside = root.appendingPathComponent("outside")
            try makeExecutable(outside)
            try FileManager.default.createSymbolicLink(at: bin.appendingPathComponent("escape"), withDestinationURL: outside)
            XCTAssertNil(resolveExecutable("escape", searchPaths: [bin.path], targetRoots: [bin.path]))
        }
    }

    func testWritableExecutableAndNestedDirectoryAreRejected() throws {
        try withHelperFixture { _, bin, cellar, helper in
            try FileManager.default.setAttributes([.posixPermissions: 0o777], ofItemAtPath: helper.path)
            XCTAssertNil(resolveExecutable("helper", searchPaths: [bin.path], targetRoots: [cellar.path]))
            try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: helper.path)
            let nested = helper.deletingLastPathComponent()
            try FileManager.default.setAttributes([.posixPermissions: 0o777], ofItemAtPath: nested.path)
            XCTAssertNil(resolveExecutable("helper", searchPaths: [bin.path], targetRoots: [cellar.path]))
        }
    }

    func testWritableSearchDirectoryIsRejected() throws {
        try withHelperFixture { _, bin, cellar, _ in
            try FileManager.default.setAttributes([.posixPermissions: 0o777], ofItemAtPath: bin.path)
            XCTAssertNil(resolveExecutable("helper", searchPaths: [bin.path], targetRoots: [cellar.path]))
        }
    }

    func testRestorationRunsOnceAndBlocksLaterWrites() {
        let lifecycle = RuntimeLifecycle()
        var events: [String] = []
        XCTAssertTrue(lifecycle.write { events.append("write"); return true })
        lifecycle.finish { events.append("restore") }
        lifecycle.finish { events.append("duplicate") }
        XCTAssertFalse(lifecycle.write { events.append("late write"); return true })
        XCTAssertEqual(events, ["write", "restore"])
    }

    func testRestorationWaitsForInflightWrite() {
        let lifecycle = RuntimeLifecycle()
        let entered = DispatchSemaphore(value: 0)
        let release = DispatchSemaphore(value: 0)
        let wrote = DispatchSemaphore(value: 0)
        let finished = DispatchSemaphore(value: 0)
        DispatchQueue.global().async {
            _ = lifecycle.write {
                entered.signal()
                _ = release.wait(timeout: .now() + 5)
                wrote.signal()
                return true
            }
        }
        XCTAssertEqual(entered.wait(timeout: .now() + 2), .success)
        DispatchQueue.global().async {
            lifecycle.finish {
                XCTAssertEqual(wrote.wait(timeout: .now()), .success)
            }
            finished.signal()
        }
        XCTAssertEqual(finished.wait(timeout: .now() + 0.05), .timedOut)
        release.signal()
        XCTAssertEqual(finished.wait(timeout: .now() + 2), .success)
        XCTAssertFalse(lifecycle.write { true })
    }

    func testStopWakesWaitAndRejectsWrites() {
        let lifecycle = RuntimeLifecycle()
        let waiting = DispatchSemaphore(value: 0)
        let finished = DispatchSemaphore(value: 0)
        DispatchQueue.global().async {
            waiting.signal()
            lifecycle.wait(seconds: 60)
            finished.signal()
        }
        XCTAssertEqual(waiting.wait(timeout: .now() + 2), .success)
        lifecycle.requestStop()
        XCTAssertEqual(finished.wait(timeout: .now() + 2), .success)
        XCTAssertTrue(lifecycle.isStopping)
        XCTAssertFalse(lifecycle.write { true })
    }

    private func makeExecutable(_ path: URL) throws {
        try Data("#!/bin/sh\nexit 0\n".utf8).write(to: path)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path.path)
    }

    private func withHelperFixture(_ body: (URL, URL, URL, URL) throws -> Void) throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("wax-helper-\(UUID().uuidString)").resolvingSymlinksInPath()
        defer { try? fm.removeItem(at: root) }
        for relative in ["", "bin", "Cellar", "Cellar/helper", "Cellar/helper/1", "Cellar/helper/1/bin"] {
            let path = relative.isEmpty ? root : root.appendingPathComponent(relative)
            try fm.createDirectory(at: path, withIntermediateDirectories: true)
            try fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path.path)
        }
        let bin = root.appendingPathComponent("bin")
        let cellar = root.appendingPathComponent("Cellar")
        let helper = cellar.appendingPathComponent("helper/1/bin/helper")
        try makeExecutable(helper)
        try fm.createSymbolicLink(at: bin.appendingPathComponent("helper"), withDestinationURL: helper)
        try body(root, bin, cellar, helper)
    }
}
