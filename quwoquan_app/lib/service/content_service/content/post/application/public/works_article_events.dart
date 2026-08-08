/// Telemetry value emitted when the embedded article reader commits a page.
final class WorksArticlePageFlipEvent {
  const WorksArticlePageFlipEvent({
    required this.fromPage,
    required this.toPage,
    required this.durationMs,
    required this.mechanism,
  });

  final int fromPage;
  final int toPage;
  final int durationMs;
  final String mechanism;

  String get direction => toPage >= fromPage ? 'forward' : 'backward';
}

/// Telemetry value emitted when an embedded article page curl is cancelled.
final class WorksArticlePageCurlAbortEvent {
  const WorksArticlePageCurlAbortEvent({
    required this.corner,
    required this.progress,
    required this.direction,
  });

  final String corner;
  final double progress;
  final String direction;
}
