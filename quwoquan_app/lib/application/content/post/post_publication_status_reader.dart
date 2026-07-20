enum ContentPostPublicationState {
  pendingReview('pending_review'),
  published('published'),
  rejected('rejected');

  const ContentPostPublicationState(this.wireValue);

  final String wireValue;

  static ContentPostPublicationState fromWire(String value) {
    return switch (value.trim()) {
      'pending_review' => ContentPostPublicationState.pendingReview,
      'published' => ContentPostPublicationState.published,
      'rejected' => ContentPostPublicationState.rejected,
      final unsupported => throw FormatException(
        'unsupported Post publication state: $unsupported',
      ),
    };
  }
}

final class ContentPostPublicationStatus {
  const ContentPostPublicationStatus({
    required this.postId,
    required this.state,
    required this.updatedAt,
    this.moderationStatus,
  });

  final String postId;
  final ContentPostPublicationState state;
  final String? moderationStatus;
  final DateTime updatedAt;
}

abstract interface class ContentPostPublicationStatusReader {
  Future<ContentPostPublicationStatus> getPostPublicationStatus(String postId);
}
