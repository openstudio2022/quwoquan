// swift-tools-version: 5.9

import Foundation
import PackageDescription

let xcodeDevDir: String = {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select")
    task.arguments = ["-p"]
    let pipe = Pipe()
    task.standardOutput = pipe
    try? task.run()
    task.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
        ?? "/Applications/Xcode.app/Contents/Developer"
}()

let package = Package(
    name: "patrol",
    defaultLocalization: "en",
    platforms: [
        .iOS(.v13),
        .macOS(.v10_14),
    ],
    products: [
        .library(name: "patrol", targets: ["patrol"]),
    ],
    dependencies: [
        .package(url: "https://github.com/robbiehanson/CocoaAsyncSocket", from: "7.6.4"),
    ],
    targets: [
        .target(
            name: "HTTPParserC",
            dependencies: [],
            path: "Sources/HTTPParserC",
            publicHeadersPath: "include"
        ),
        .target(
            name: "patrol",
            dependencies: [
                .product(name: "CocoaAsyncSocket", package: "CocoaAsyncSocket"),
                "HTTPParserC",
            ],
            path: "Sources/patrol",
            resources: [
                .process("Resources/PrivacyInfo.xcprivacy"),
                .process("Resources/en.lproj"),
                .process("Resources/de.lproj"),
                .process("Resources/fr.lproj"),
                .process("Resources/pl.lproj"),
            ],
            linkerSettings: [
                .unsafeFlags([
                    "-F", "\(xcodeDevDir)/Platforms/iPhoneSimulator.platform/Developer/Library/Frameworks",
                    "-F", "\(xcodeDevDir)/Platforms/iPhoneOS.platform/Developer/Library/Frameworks",
                    "-F", "\(xcodeDevDir)/Platforms/MacOSX.platform/Developer/Library/Frameworks",
                    "-L", "\(xcodeDevDir)/Platforms/iPhoneSimulator.platform/Developer/usr/lib",
                    "-L", "\(xcodeDevDir)/Platforms/iPhoneOS.platform/Developer/usr/lib",
                    "-L", "\(xcodeDevDir)/Platforms/MacOSX.platform/Developer/usr/lib",
                    "-weak_framework", "XCTest",
                ]),
                .linkedFramework("UIKit", .when(platforms: [.iOS])),
                .linkedFramework("AppKit", .when(platforms: [.macOS])),
            ]
        ),
    ]
)
