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
    ],
    targets: [
        .target(
            name: "livekit_client",
            dependencies: [
                .product(name: "flutter-webrtc", package: "flutter_webrtc"),
            ],
            path: "Sources/livekit_client",
            linkerSettings: [
                .linkedFramework("AVFoundation"),
                .linkedFramework("Accelerate"),
                .linkedFramework("ReplayKit"),
                .linkedFramework("UIKit"),
            ]
        ),
    ]
)
