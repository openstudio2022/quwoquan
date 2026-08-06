/// Circle-owned request for its viewer-to-circle intersection summary.
final class CircleIntersectionSummaryRequest {
  const CircleIntersectionSummaryRequest({
    required this.viewerId,
    required this.circleId,
    this.limit = 6,
  });

  final String viewerId;
  final String circleId;
  final int limit;

  bool get isResolvable => viewerId.isNotEmpty && circleId.isNotEmpty;
}

/// Circle-owned request for the recommendation impact preview.
final class CircleImpactPreviewRequest {
  const CircleImpactPreviewRequest({
    required this.circleId,
    required this.referralSource,
  });

  final String circleId;
  final String referralSource;
}
