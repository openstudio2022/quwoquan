// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "livekit_client",
    platforms: [
        .iOS(.v13),
    ],
    products: [
        .library(name: "livekit-client", targets: ["livekit_client"]),
    ],
    dependencies: [
        .package(name: "flutter_webrtc", path: "../flutter_webrtc"),
        .package(url: "https://github.com/webrtc-sdk/Specs.git", exact: "144.7559.01"),
    ],
    targets: [
        .target(
            name: "livekit_client",
            dependencies: [
                .product(name: "flutter-webrtc", package: "flutter_webrtc"),
                .product(name: "WebRTC", package: "Specs"),
            ],
            path: "../Classes",
            linkerSettings: [
                .linkedFramework("Accelerate"),
                .linkedFramework("AVFoundation"),
                .linkedFramework("CoreMedia"),
                .linkedFramework("ReplayKit"),
            ]
        ),
    ]
)
