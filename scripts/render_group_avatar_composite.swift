import AppKit
import Foundation

enum RenderError: Error, CustomStringConvertible {
    case invalidArguments
    case cannotLoadImage(String)
    case cannotCreateContext
    case cannotCreatePNG

    var description: String {
        switch self {
        case .invalidArguments:
            return "usage: swift render_group_avatar_composite.swift <output-path> <input-image> [<input-image>...]"
        case let .cannotLoadImage(path):
            return "cannot load image: \(path)"
        case .cannotCreateContext:
            return "cannot create bitmap context"
        case .cannotCreatePNG:
            return "cannot encode composite png"
        }
    }
}

func gridDimension(for count: Int) -> Int {
    switch count {
    case ...1:
        return 1
    case 2...4:
        return 2
    default:
        return 3
    }
}

func drawAspectFill(image: NSImage, in targetRect: NSRect) {
    guard let rep = image.bestRepresentation(for: targetRect, context: nil, hints: nil) else {
        image.draw(in: targetRect)
        return
    }
    let sourceSize = NSSize(width: rep.pixelsWide, height: rep.pixelsHigh)
    if sourceSize.width <= 0 || sourceSize.height <= 0 {
        image.draw(in: targetRect)
        return
    }

    let scale = max(targetRect.width / sourceSize.width, targetRect.height / sourceSize.height)
    let drawSize = NSSize(width: sourceSize.width * scale, height: sourceSize.height * scale)
    let drawOrigin = NSPoint(
        x: targetRect.origin.x + (targetRect.width - drawSize.width) / 2.0,
        y: targetRect.origin.y + (targetRect.height - drawSize.height) / 2.0
    )
    let drawRect = NSRect(origin: drawOrigin, size: drawSize)
    NSGraphicsContext.current?.imageInterpolation = .high
    image.draw(in: drawRect, from: .zero, operation: .copy, fraction: 1.0)
}

func renderComposite(outputURL: URL, inputURLs: [URL]) throws {
    let images = try inputURLs.map { url -> NSImage in
        guard let image = NSImage(contentsOf: url) else {
            throw RenderError.cannotLoadImage(url.path)
        }
        return image
    }

    let canvasSize = NSSize(width: 256, height: 256)
    guard let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: Int(canvasSize.width),
        pixelsHigh: Int(canvasSize.height),
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ) else {
        throw RenderError.cannotCreateContext
    }

    bitmap.size = canvasSize
    guard let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        throw RenderError.cannotCreateContext
    }

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context

    let background = NSColor(calibratedWhite: 0.95, alpha: 1.0)
    background.setFill()
    NSBezierPath(rect: NSRect(origin: .zero, size: canvasSize)).fill()

    let grid = gridDimension(for: images.count)
    let gap: CGFloat = grid == 1 ? 0 : 4
    let totalGap = gap * CGFloat(max(0, grid - 1))
    let cell = (canvasSize.width - totalGap) / CGFloat(grid)

    for (index, image) in images.enumerated() {
        let row = index / grid
        let column = index % grid
        let x = CGFloat(column) * (cell + gap)
        let y = canvasSize.height - CGFloat(row + 1) * cell - CGFloat(row) * gap
        let rect = NSRect(x: x, y: y, width: cell, height: cell)

        let clip = NSBezierPath(roundedRect: rect, xRadius: grid == 1 ? 28 : 18, yRadius: grid == 1 ? 28 : 18)
        clip.addClip()
        drawAspectFill(image: image, in: rect)
        NSGraphicsContext.current?.restoreGraphicsState()
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context
    }

    NSGraphicsContext.restoreGraphicsState()

    guard let data = bitmap.representation(using: .png, properties: [:]) else {
        throw RenderError.cannotCreatePNG
    }

    try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try data.write(to: outputURL)
}

do {
    let args = CommandLine.arguments
    guard args.count >= 3 else {
        throw RenderError.invalidArguments
    }
    let outputURL = URL(fileURLWithPath: args[1])
    let inputURLs = args.dropFirst(2).map { URL(fileURLWithPath: $0) }
    try renderComposite(outputURL: outputURL, inputURLs: inputURLs)
} catch let error as RenderError {
    fputs("\(error)\n", stderr)
    exit(1)
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}
