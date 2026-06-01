// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "flutter_webrtc",
    platforms: [
        .iOS(.v13),
    ],
    products: [
        .library(name: "flutter-webrtc", targets: ["flutter_webrtc"]),
    ],
    dependencies: [
        .package(url: "https://github.com/webrtc-sdk/Specs.git", exact: "144.7559.01"),
    ],
    targets: [
        .target(
            name: "flutter_webrtc",
            dependencies: [
                .product(name: "WebRTC", package: "Specs"),
            ],
            path: "Sources/flutter_webrtc",
            exclude: [
                "include",
                "Broadcast",
                "RTCAudioSource+Private.h",
                "media_stream_interface.h",
            ],
            publicHeadersPath: "include",
            cSettings: [
                .headerSearchPath("."),
                .headerSearchPath("Broadcast"),
                .headerSearchPath("include"),
            ],
            cxxSettings: [
                .headerSearchPath("."),
                .headerSearchPath("Broadcast"),
                .headerSearchPath("include"),
            ],
            linkerSettings: [
                .linkedLibrary("c++"),
                .linkedFramework("AVFoundation"),
                .linkedFramework("CoreMedia"),
                .linkedFramework("ReplayKit"),
                .linkedFramework("UIKit"),
            ]
        ),
    ]
)
