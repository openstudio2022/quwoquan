// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "video_thumbnail",
    platforms: [
        .iOS(.v13),
    ],
    products: [
        .library(name: "video-thumbnail", targets: ["video_thumbnail"]),
    ],
    dependencies: [
        .package(url: "https://github.com/SDWebImage/libwebp-Xcode.git", from: "1.5.0"),
    ],
    targets: [
        .target(
            name: "video_thumbnail",
            dependencies: [
                .product(name: "libwebp", package: "libwebp-Xcode"),
            ],
            path: "Sources/video_thumbnail"
        ),
    ]
)
