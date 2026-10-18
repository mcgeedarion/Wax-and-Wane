import Foundation
import XCTest
@testable import WaxAndWaneCore

final class CLIConfigTests: XCTestCase {
    private func writeConfig(overrides: [String: Any]) throws -> String {
        let defaultData = try XCTUnwrap(defaultConfigJSON().data(using: .utf8))
        var config = try XCTUnwrap(JSONSerialization.jsonObject(with: defaultData) as? [String: Any])
        for (key, value) in overrides {
            config[key] = value
        }
        let data = try JSONSerialization.data(withJSONObject: config, options: [.prettyPrinted, .sortedKeys])
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("wax-and-wane-")
            .appendingPathExtension(UUID().uuidString)
        try data.write(to: url)
        return url.path
    }

    func testConfigBooleanValuesSurviveWhenFlagsAreAbsent() throws {
        let path = try writeConfig(overrides: [
            "dryRun": true,
            "invertKeyboard": true,
            "invertScreen": true,
            "restoreOriginalBrightness": false,
        ])
        defer { try? FileManager.default.removeItem(atPath: path) }

        let command = try Run.parse(["--config", path])
        let settings = try command.buildSettings(cliArguments: ["wax-and-wane", "run", "--config", path])

        XCTAssertTrue(settings.dryRun)
        XCTAssertTrue(settings.invertKeyboard)
        XCTAssertTrue(settings.invertScreen)
        XCTAssertFalse(settings.restoreOriginalBrightness)
    }

    func testExplicitBooleanFlagsOverrideConfigValues() throws {
        let path = try writeConfig(overrides: [
            "dryRun": false,
            "invertKeyboard": false,
            "invertScreen": false,
            "restoreOriginalBrightness": true,
        ])
        defer { try? FileManager.default.removeItem(atPath: path) }

        let args = [
            "--config", path,
            "--dry-run",
            "--invert-keyboard",
            "--invert-screen",
            "--no-restore-original-brightness",
        ]
        let command = try Run.parse(args)
        let settings = try command.buildSettings(cliArguments: ["wax-and-wane", "run"] + args)

        XCTAssertTrue(settings.dryRun)
        XCTAssertTrue(settings.invertKeyboard)
        XCTAssertTrue(settings.invertScreen)
        XCTAssertFalse(settings.restoreOriginalBrightness)
    }


    func testPartialConfigInheritsBuiltInDefaults() throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("wax-and-wane-partial-\(UUID().uuidString).json")
        try Data("{\"pollIntervalSeconds\": 3.5}".utf8).write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }

        let settings = try loadConfig(path: url.path)
        XCTAssertEqual(settings.pollIntervalSeconds, 3.5)
        XCTAssertEqual(settings.smoothingWindow, 5)
        XCTAssertEqual(settings.screenMin, 0.2)
    }

    func testRejectsNonFiniteSettings() {
        var settings = Settings()
        settings.outputGamma = .infinity
        XCTAssertThrowsError(try validateSettings(settings))

        settings = Settings()
        settings.pollIntervalSeconds = .nan
        XCTAssertThrowsError(try validateSettings(settings))
    }

    func testNegativeInvertFlagsOverrideConfig() throws {
        let path = try writeConfig(overrides: ["invertKeyboard": true, "invertScreen": true])
        defer { try? FileManager.default.removeItem(atPath: path) }
        let args = ["--config", path, "--no-invert-keyboard", "--no-invert-screen"]
        let command = try Run.parse(args)
        let settings = try command.buildSettings(cliArguments: ["wax-and-wane", "run"] + args)
        XCTAssertFalse(settings.invertKeyboard)
        XCTAssertFalse(settings.invertScreen)
    }

    func testRunSubcommandParsesDocumentedInvocation() throws {
        XCTAssertNoThrow(try CLI.parseAsRoot(["run", "--dry-run", "--max-runtime", "1"]))
    }

    func testDefaultRunParsesWithoutSubcommand() throws {
        XCTAssertNoThrow(try CLI.parseAsRoot(["--dry-run", "--max-runtime", "1"]))
    }
}
