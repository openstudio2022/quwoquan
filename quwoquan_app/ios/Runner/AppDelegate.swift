import AVFoundation
import CoreGraphics
import CoreLocation
import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private let processStartUptime = ProcessInfo.processInfo.systemUptime
  private let videoEditingPlugin = VideoEditingPlugin()
  private let personalAssistantNativeApiPlugin = PersonalAssistantNativeApiPlugin()
  private let commercialAuthPlugin = CommercialAuthPlugin()
  private let aliyunOneTapPlugin = AliyunOneTapPlugin()

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    NSLog("QWQStartup ios_did_finish_launching")
    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)
    if let registrar = self.registrar(forPlugin: "QuwoquanNativeMethodChannels") {
      registerMethodChannels(binaryMessenger: registrar.messenger())
    }
    window?.backgroundColor = StartupTransitionBackground.color
    window?.rootViewController?.view.backgroundColor = StartupTransitionBackground.color
    return launched
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    NSLog("QWQStartup ios_implicit_flutter_engine_initialized")
    registerStartupTimingsChannel(
      binaryMessenger: engineBridge.applicationRegistrar.messenger()
    )
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    registerMethodChannels(
      binaryMessenger: engineBridge.applicationRegistrar.messenger(),
      includeStartupTimings: false
    )
  }

  private func registerMethodChannels(
    binaryMessenger: FlutterBinaryMessenger,
    includeStartupTimings: Bool = true
  ) {
    if includeStartupTimings {
      registerStartupTimingsChannel(binaryMessenger: binaryMessenger)
    }

    let videoEditingChannel = FlutterMethodChannel(
      name: "quwoquan/video_editing",
      binaryMessenger: binaryMessenger
    )
    videoEditingChannel.setMethodCallHandler { [weak self] call, result in
      self?.videoEditingPlugin.handle(call: call, result: result)
    }

    let assistantChannel = FlutterMethodChannel(
      name: "personal_assistant/native_api",
      binaryMessenger: binaryMessenger
    )
    assistantChannel.setMethodCallHandler { [weak self] call, result in
      self?.personalAssistantNativeApiPlugin.handle(call: call, result: result)
    }

    let nativeAuthChannel = FlutterMethodChannel(
      name: "quwoquan/auth/native_bridge",
      binaryMessenger: binaryMessenger
    )
    nativeAuthChannel.setMethodCallHandler { [weak self] call, result in
      self?.commercialAuthPlugin.handle(call: call, result: result)
    }

    let oneTapLoginChannel = FlutterMethodChannel(
      name: "quwoquan/auth/one_tap",
      binaryMessenger: binaryMessenger
    )
    oneTapLoginChannel.setMethodCallHandler { [weak self] call, result in
      self?.aliyunOneTapPlugin.handle(call: call, result: result)
    }
  }

  private func registerStartupTimingsChannel(
    binaryMessenger: FlutterBinaryMessenger
  ) {
    let startupTimingsChannel = FlutterMethodChannel(
      name: "quwoquan/startup/timings",
      binaryMessenger: binaryMessenger
    )
    startupTimingsChannel.setMethodCallHandler { [weak self] call, result in
      if call.method == "recordStartupEvent" {
        let event = call.arguments as? String ?? "{}"
        NSLog("QWQStartup startup_event %@", event)
        result(nil)
        return
      }
      guard call.method == "readProcessSegments" else {
        result(FlutterMethodNotImplemented)
        return
      }
      guard let self else {
        result(nil)
        return
      }
      let elapsedMs = Int(
        (ProcessInfo.processInfo.systemUptime - self.processStartUptime) * 1000
      )
      result([
        "elapsedSinceProcessStartMs": elapsedMs,
        "deadlineOrigin": "ios_process",
      ])
    }
  }

  override func application(
    _ app: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey: Any] = [:]
  ) -> Bool {
    if commercialAuthPlugin.handle(url: url) {
      return true
    }
    return super.application(app, open: url, options: options)
  }

  override func application(
    _ application: UIApplication,
    continue userActivity: NSUserActivity,
    restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
  ) -> Bool {
    if commercialAuthPlugin.handle(userActivity: userActivity) {
      return true
    }
    return super.application(
      application,
      continue: userActivity,
      restorationHandler: restorationHandler
    )
  }
}

private enum StartupTransitionBackground {
  static let color = UIColor(
    red: 0.0392156863,
    green: 0.5176470588,
    blue: 1.0,
    alpha: 1
  )
}

private final class PersonalAssistantNativeApiPlugin {
  func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "getLocalContext":
      handleGetLocalContext(call: call, result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func handleGetLocalContext(
    call: FlutterMethodCall,
    result: @escaping FlutterResult
  ) {
    let arguments = call.arguments as? [String: Any] ?? [:]
    let requestedFields = Set((arguments["requestedFields"] as? [String] ?? []))
    let includeLocation = requestedFields.isEmpty || requestedFields.contains("location")
    let includePermissions = requestedFields.isEmpty || requestedFields.contains("permissions")
    let includeDevice = requestedFields.isEmpty || requestedFields.contains("device")

    var payload: [String: Any] = [:]
    let locale = Locale.preferredLanguages.first ?? Locale.current.identifier
    let timezone = TimeZone.current.identifier

    if includeDevice {
      payload["device"] = [
        "os": "iOS",
        "model": UIDevice.current.model,
        "locale": locale,
        "timezone": timezone,
      ]
    }

    let authorizationStatus = CLLocationManager.authorizationStatus()
    if includePermissions {
      payload["permissions"] = [
        "location": locationPermissionLabel(for: authorizationStatus),
      ]
    }

    guard includeLocation else {
      result(payload)
      return
    }

    let manager = CLLocationManager()
    guard
      authorizationStatus == .authorizedAlways ||
      authorizationStatus == .authorizedWhenInUse
    else {
      result(payload)
      return
    }

    guard let location = manager.location else {
      result(payload)
      return
    }

    var locationPayload: [String: Any] = [
      "latitude": location.coordinate.latitude,
      "longitude": location.coordinate.longitude,
      "accuracyM": location.horizontalAccuracy,
      "source": "core_location",
    ]

    CLGeocoder().reverseGeocodeLocation(location) { placemarks, _ in
      if let placemark = placemarks?.first {
        let city = placemark.locality ?? placemark.subAdministrativeArea ?? ""
        if !city.isEmpty {
          payload["city"] = city
          payload["currentCity"] = city
          locationPayload["city"] = city
        }
        let countryCode = placemark.isoCountryCode ?? ""
        if !countryCode.isEmpty {
          locationPayload["countryCode"] = countryCode
        }
      }
      payload["locationSource"] = "core_location"
      payload["location"] = locationPayload
      payload["gpsLocation"] = locationPayload
      result(payload)
    }
  }

  private func locationPermissionLabel(for status: CLAuthorizationStatus) -> String {
    switch status {
    case .authorizedAlways, .authorizedWhenInUse:
      return "granted"
    case .denied:
      return "denied"
    case .restricted:
      return "restricted"
    case .notDetermined:
      return "not_determined"
    @unknown default:
      return "unknown"
    }
  }
}

private final class VideoEditingPlugin {
  private let queue = DispatchQueue(label: "quwoquan.video_editing", qos: .userInitiated)

  func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "extractVideoFrames":
      guard let arguments = call.arguments as? [String: Any] else {
        result(VideoEditingError.invalidArguments.flutterError)
        return
      }
      handleExtractFrames(arguments: arguments, result: result)
    case "exportVideoEdit":
      guard let arguments = call.arguments as? [String: Any] else {
        result(VideoEditingError.invalidArguments.flutterError)
        return
      }
      handleExportVideoEdit(arguments: arguments, result: result)
    case "composeOneTapMovie":
      guard let arguments = call.arguments as? [String: Any] else {
        result(VideoEditingError.invalidArguments.flutterError)
        return
      }
      handleComposeOneTapMovie(arguments: arguments, result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func handleExtractFrames(
    arguments: [String: Any],
    result: @escaping FlutterResult
  ) {
    queue.async {
      do {
        let request = try FrameExtractionRequest(arguments: arguments)
        let frames = try self.extractFrames(request: request)
        DispatchQueue.main.async {
          result(frames)
        }
      } catch let error as VideoEditingError {
        DispatchQueue.main.async {
          result(error.flutterError)
        }
      } catch {
        DispatchQueue.main.async {
          result(VideoEditingError.unknown(error.localizedDescription).flutterError)
        }
      }
    }
  }

  private func handleExportVideoEdit(
    arguments: [String: Any],
    result: @escaping FlutterResult
  ) {
    do {
      let request = try VideoEditRequest(arguments: arguments)
      let asset = AVURLAsset(url: URL(fileURLWithPath: request.sourcePath))
      let composition = try makeComposition(asset: asset, request: request)
      let outputURL = try makeOutputURL(prefix: "edited_video", fileExtension: "mp4")
      guard let exportSession = AVAssetExportSession(
        asset: composition,
        presetName: AVAssetExportPresetHighestQuality
      ) else {
        result(VideoEditingError.exportUnavailable.flutterError)
        return
      }

      let supportedTypes = exportSession.supportedFileTypes
      if supportedTypes.contains(.mp4) {
        exportSession.outputFileType = .mp4
      } else if let first = supportedTypes.first {
        exportSession.outputFileType = first
      } else {
        result(VideoEditingError.exportUnavailable.flutterError)
        return
      }
      exportSession.outputURL = outputURL
      exportSession.shouldOptimizeForNetworkUse = true

      exportSession.exportAsynchronously { [weak self] in
        guard let self else { return }
        switch exportSession.status {
        case .completed:
          self.queue.async {
            do {
              let coverPath = try self.generateCoverImage(
                sourcePath: request.sourcePath,
                timeMs: request.coverTimeMs
              )
              let payload: [String: Any] = [
                "videoPath": outputURL.path,
                "coverPath": coverPath,
                "durationMs": Int(CMTimeGetSeconds(composition.duration) * 1000),
              ]
              DispatchQueue.main.async {
                result(payload)
              }
            } catch let error as VideoEditingError {
              DispatchQueue.main.async {
                result(error.flutterError)
              }
            } catch {
              DispatchQueue.main.async {
                result(VideoEditingError.unknown(error.localizedDescription).flutterError)
              }
            }
          }
        case .failed:
          let message = exportSession.error?.localizedDescription ?? "Video export failed."
          DispatchQueue.main.async {
            result(VideoEditingError.exportFailed(message).flutterError)
          }
        case .cancelled:
          DispatchQueue.main.async {
            result(VideoEditingError.exportFailed("Video export cancelled.").flutterError)
          }
        default:
          let message = exportSession.error?.localizedDescription ?? "Video export pending."
          DispatchQueue.main.async {
            result(VideoEditingError.exportFailed(message).flutterError)
          }
        }
      }
    } catch let error as VideoEditingError {
      result(error.flutterError)
    } catch {
      result(VideoEditingError.unknown(error.localizedDescription).flutterError)
    }
  }

  private func handleComposeOneTapMovie(
    arguments: [String: Any],
    result: @escaping FlutterResult
  ) {
    queue.async {
      do {
        let request = try OneTapMovieRequest(arguments: arguments)
        let payload = try self.composeOneTapMovie(request: request)
        DispatchQueue.main.async {
          result(payload)
        }
      } catch let error as VideoEditingError {
        DispatchQueue.main.async {
          result(error.flutterError)
        }
      } catch {
        DispatchQueue.main.async {
          result(VideoEditingError.unknown(error.localizedDescription).flutterError)
        }
      }
    }
  }

  private func extractFrames(
    request: FrameExtractionRequest
  ) throws -> [[String: Any]] {
    let asset = AVURLAsset(url: URL(fileURLWithPath: request.sourcePath))
    let durationMs = max(Int(CMTimeGetSeconds(asset.duration) * 1000), 1000)
    let startMs = min(max(request.startMs, 0), durationMs - 1)
    let endMs = max(min(request.endMs, durationMs), startMs + 100)
    let count = max(request.frameCount, 1)
    let step = count == 1 ? 0 : (endMs - startMs) / max(count - 1, 1)

    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.maximumSize = CGSize(
      width: request.maxDimension,
      height: request.maxDimension
    )

    var frames: [[String: Any]] = []
    for index in 0..<count {
      let timeMs = startMs + step * index
      let time = CMTime(value: CMTimeValue(timeMs), timescale: 1000)
      let image = try generator.copyCGImage(at: time, actualTime: nil)
      let path = try writeImage(image, prefix: "frame_\(index)")
      frames.append([
        "path": path,
        "timeMs": timeMs,
      ])
    }
    return frames
  }

  private func makeComposition(
    asset: AVAsset,
    request: VideoEditRequest
  ) throws -> AVMutableComposition {
    guard let sourceVideoTrack = asset.tracks(withMediaType: .video).first else {
      throw VideoEditingError.videoTrackMissing
    }
    let composition = AVMutableComposition()
    guard let videoTrack = composition.addMutableTrack(
      withMediaType: .video,
      preferredTrackID: kCMPersistentTrackID_Invalid
    ) else {
      throw VideoEditingError.exportUnavailable
    }
    let timeRange = request.makeTimeRange(duration: asset.duration)
    try videoTrack.insertTimeRange(timeRange, of: sourceVideoTrack, at: .zero)
    videoTrack.preferredTransform = sourceVideoTrack.preferredTransform

    if !request.muted {
      for audioSourceTrack in asset.tracks(withMediaType: .audio) {
        let audioTrack = composition.addMutableTrack(
          withMediaType: .audio,
          preferredTrackID: kCMPersistentTrackID_Invalid
        )
        try audioTrack?.insertTimeRange(timeRange, of: audioSourceTrack, at: .zero)
      }
    }
    return composition
  }

  private func composeOneTapMovie(request: OneTapMovieRequest) throws -> [String: Any] {
    let outputURL = try makeOutputURL(prefix: "one_tap_movie", fileExtension: "mp4")
    let renderSize = CGSize(width: request.outputWidth, height: request.outputHeight)
    let writer = try AVAssetWriter(outputURL: outputURL, fileType: .mp4)
    let settings: [String: Any] = [
      AVVideoCodecKey: AVVideoCodecType.h264,
      AVVideoWidthKey: request.outputWidth,
      AVVideoHeightKey: request.outputHeight,
    ]
    let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
    input.expectsMediaDataInRealTime = false
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(
      assetWriterInput: input,
      sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
        kCVPixelBufferWidthKey as String: request.outputWidth,
        kCVPixelBufferHeightKey as String: request.outputHeight,
        kCVPixelBufferCGImageCompatibilityKey as String: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey as String: true,
      ]
    )
    guard writer.canAdd(input) else {
      throw VideoEditingError.exportUnavailable
    }
    writer.add(input)
    guard writer.startWriting() else {
      throw VideoEditingError.exportFailed(writer.error?.localizedDescription ?? "Unable to start writer.")
    }
    writer.startSession(atSourceTime: .zero)

    let frameDuration = CMTime(value: 1, timescale: 30)
    for (index, path) in request.imagePaths.enumerated() {
      guard let image = UIImage(contentsOfFile: path) else {
        throw VideoEditingError.imageReadFailed(path)
      }
      let start = CMTime(value: CMTimeValue(index * request.secondsPerImage), timescale: 1)
      try appendImageFrame(
        image,
        renderSize: renderSize,
        at: start,
        input: input,
        adaptor: adaptor
      )
      let next = CMTime(
        value: CMTimeValue((index + 1) * request.secondsPerImage),
        timescale: 1
      )
      let end = CMTimeSubtract(next, frameDuration)
      if CMTimeCompare(end, start) > 0 {
        try appendImageFrame(
          image,
          renderSize: renderSize,
          at: end,
          input: input,
          adaptor: adaptor
        )
      }
    }

    input.markAsFinished()
    let semaphore = DispatchSemaphore(value: 0)
    writer.finishWriting {
      semaphore.signal()
    }
    semaphore.wait()
    guard writer.status == .completed else {
      throw VideoEditingError.exportFailed(
        writer.error?.localizedDescription ?? "One-tap movie export failed."
      )
    }
    let coverPath = try writeUIImage(
      UIImage(contentsOfFile: request.imagePaths[0]) ?? UIImage(),
      prefix: "one_tap_movie_cover"
    )
    return [
      "videoPath": outputURL.path,
      "coverPath": coverPath,
      "durationMs": request.imagePaths.count * request.secondsPerImage * 1000,
    ]
  }

  private func appendImageFrame(
    _ image: UIImage,
    renderSize: CGSize,
    at time: CMTime,
    input: AVAssetWriterInput,
    adaptor: AVAssetWriterInputPixelBufferAdaptor
  ) throws {
    while !input.isReadyForMoreMediaData {
      Thread.sleep(forTimeInterval: 0.01)
    }
    guard let buffer = makePixelBuffer(from: image, renderSize: renderSize) else {
      throw VideoEditingError.pixelBufferFailed
    }
    guard adaptor.append(buffer, withPresentationTime: time) else {
      throw VideoEditingError.exportFailed("Unable to append one-tap movie frame.")
    }
  }

  private func makePixelBuffer(from image: UIImage, renderSize: CGSize) -> CVPixelBuffer? {
    var pixelBuffer: CVPixelBuffer?
    let status = CVPixelBufferCreate(
      kCFAllocatorDefault,
      Int(renderSize.width),
      Int(renderSize.height),
      kCVPixelFormatType_32BGRA,
      [
        kCVPixelBufferCGImageCompatibilityKey: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey: true,
      ] as CFDictionary,
      &pixelBuffer
    )
    guard status == kCVReturnSuccess, let buffer = pixelBuffer else {
      return nil
    }
    CVPixelBufferLockBaseAddress(buffer, [])
    defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
    guard
      let context = CGContext(
        data: CVPixelBufferGetBaseAddress(buffer),
        width: Int(renderSize.width),
        height: Int(renderSize.height),
        bitsPerComponent: 8,
        bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue |
          CGBitmapInfo.byteOrder32Little.rawValue
      )
    else {
      return nil
    }
    UIGraphicsPushContext(context)
    UIColor.black.setFill()
    UIRectFill(CGRect(origin: .zero, size: renderSize))
    image.draw(in: aspectFitRect(imageSize: image.size, canvasSize: renderSize))
    UIGraphicsPopContext()
    return buffer
  }

  private func aspectFitRect(imageSize: CGSize, canvasSize: CGSize) -> CGRect {
    guard imageSize.width > 0 && imageSize.height > 0 else {
      return CGRect(origin: .zero, size: canvasSize)
    }
    let scale = min(canvasSize.width / imageSize.width, canvasSize.height / imageSize.height)
    let width = imageSize.width * scale
    let height = imageSize.height * scale
    return CGRect(
      x: (canvasSize.width - width) / 2,
      y: (canvasSize.height - height) / 2,
      width: width,
      height: height
    )
  }

  private func generateCoverImage(sourcePath: String, timeMs: Int) throws -> String {
    let asset = AVURLAsset(url: URL(fileURLWithPath: sourcePath))
    let durationMs = max(Int(CMTimeGetSeconds(asset.duration) * 1000), 1000)
    let clampedTimeMs = min(max(timeMs, 0), durationMs - 1)
    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.maximumSize = CGSize(width: 720, height: 720)
    let time = CMTime(value: CMTimeValue(clampedTimeMs), timescale: 1000)
    let image = try generator.copyCGImage(at: time, actualTime: nil)
    return try writeImage(image, prefix: "cover")
  }

  private func writeImage(_ image: CGImage, prefix: String) throws -> String {
    return try writeUIImage(UIImage(cgImage: image), prefix: prefix)
  }

  private func writeUIImage(_ image: UIImage, prefix: String) throws -> String {
    let url = try makeOutputURL(prefix: prefix, fileExtension: "jpg")
    guard let data = image.jpegData(compressionQuality: 0.9) else {
      throw VideoEditingError.imageWriteFailed
    }
    try data.write(to: url, options: .atomic)
    return url.path
  }

  private func makeOutputURL(prefix: String, fileExtension: String) throws -> URL {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("quwoquan_video_editing", isDirectory: true)
    try FileManager.default.createDirectory(
      at: directory,
      withIntermediateDirectories: true,
      attributes: nil
    )
    let fileName = "\(prefix)_\(UUID().uuidString).\(fileExtension)"
    let outputURL = directory.appendingPathComponent(fileName)
    if FileManager.default.fileExists(atPath: outputURL.path) {
      try FileManager.default.removeItem(at: outputURL)
    }
    return outputURL
  }
}

private struct FrameExtractionRequest {
  init(arguments: [String: Any]) throws {
    guard let sourcePath = arguments["sourcePath"] as? String, !sourcePath.isEmpty else {
      throw VideoEditingError.invalidArguments
    }
    self.sourcePath = sourcePath
    self.startMs = arguments["startMs"] as? Int ?? 0
    self.endMs = arguments["endMs"] as? Int ?? 0
    self.frameCount = arguments["frameCount"] as? Int ?? 12
    self.maxDimension = arguments["maxDimension"] as? Int ?? 360
  }

  let sourcePath: String
  let startMs: Int
  let endMs: Int
  let frameCount: Int
  let maxDimension: Int
}

private struct VideoEditRequest {
  init(arguments: [String: Any]) throws {
    guard let sourcePath = arguments["sourcePath"] as? String, !sourcePath.isEmpty else {
      throw VideoEditingError.invalidArguments
    }
    self.sourcePath = sourcePath
    self.trimStartMs = arguments["trimStartMs"] as? Int ?? 0
    self.trimEndMs = arguments["trimEndMs"] as? Int ?? 0
    self.muted = arguments["muted"] as? Bool ?? false
    self.coverTimeMs = arguments["coverTimeMs"] as? Int ?? 0
  }

  let sourcePath: String
  let trimStartMs: Int
  let trimEndMs: Int
  let muted: Bool
  let coverTimeMs: Int

  var trimmedDurationMs: Int {
    let end = trimEndMs > trimStartMs ? trimEndMs : trimStartMs
    return max(end - trimStartMs, 0)
  }

  func makeTimeRange(duration: CMTime) -> CMTimeRange {
    let totalMs = max(Int(CMTimeGetSeconds(duration) * 1000), 1000)
    let start = min(max(trimStartMs, 0), totalMs - 1)
    let endCandidate = trimEndMs > 0 ? trimEndMs : totalMs
    let end = max(min(endCandidate, totalMs), start + 100)
    let startTime = CMTime(value: CMTimeValue(start), timescale: 1000)
    let endTime = CMTime(value: CMTimeValue(end), timescale: 1000)
    return CMTimeRange(start: startTime, end: endTime)
  }
}

private struct OneTapMovieRequest {
  init(arguments: [String: Any]) throws {
    let rawImagePaths = arguments["imagePaths"] as? [String] ?? []
    let imagePaths = rawImagePaths
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    guard !imagePaths.isEmpty else {
      throw VideoEditingError.invalidArguments
    }
    self.imagePaths = imagePaths
    self.secondsPerImage = max(arguments["secondsPerImage"] as? Int ?? 3, 1)
    self.outputWidth = max(arguments["outputWidth"] as? Int ?? 1080, 320)
    self.outputHeight = max(arguments["outputHeight"] as? Int ?? 1920, 320)
  }

  let imagePaths: [String]
  let secondsPerImage: Int
  let outputWidth: Int
  let outputHeight: Int
}

private enum VideoEditingError: Error {
  case invalidArguments
  case videoTrackMissing
  case exportUnavailable
  case exportFailed(String)
  case imageReadFailed(String)
  case imageWriteFailed
  case pixelBufferFailed
  case unknown(String)

  var flutterError: FlutterError {
    switch self {
    case .invalidArguments:
      return FlutterError(
        code: "video_edit_invalid_arguments",
        message: "Invalid video editing arguments.",
        details: nil
      )
    case .videoTrackMissing:
      return FlutterError(
        code: "video_edit_missing_track",
        message: "Video track missing.",
        details: nil
      )
    case .exportUnavailable:
      return FlutterError(
        code: "video_edit_export_unavailable",
        message: "Unable to create export session.",
        details: nil
      )
    case let .exportFailed(message):
      return FlutterError(
        code: "video_edit_export_failed",
        message: message,
        details: nil
      )
    case let .imageReadFailed(path):
      return FlutterError(
        code: "video_edit_image_read_failed",
        message: "Unable to read image: \(path)",
        details: nil
      )
    case .imageWriteFailed:
      return FlutterError(
        code: "video_edit_image_write_failed",
        message: "Unable to write thumbnail image.",
        details: nil
      )
    case .pixelBufferFailed:
      return FlutterError(
        code: "video_edit_pixel_buffer_failed",
        message: "Unable to render one-tap movie frame.",
        details: nil
      )
    case let .unknown(message):
      return FlutterError(
        code: "video_edit_unknown",
        message: message,
        details: nil
      )
    }
  }
}
