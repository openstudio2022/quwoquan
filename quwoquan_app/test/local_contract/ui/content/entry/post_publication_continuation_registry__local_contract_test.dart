// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/post/post_publication_continuation_registry.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'registry dispatches one canonical operation and rejects unknown ids',
    () async {
      final handler = _RecordingHandler();
      final registry = PostPublicationContinuationRegistry(
        <PostPublicationContinuationHandler>[handler],
      );
      final receipt = _receipt();
      const continuation = CreateDraftPublicationContinuationRef(
        operationId: 'travel.content_link.put',
        sourceEntityRef: 'travel.TripShareSnapshot:share-1@1',
      );

      await registry.apply(continuation: continuation, receipt: receipt);

      expect(handler.continuations, <CreateDraftPublicationContinuationRef>[
        continuation,
      ]);
      await expectLater(
        registry.apply(
          continuation: const CreateDraftPublicationContinuationRef(
            operationId: 'unknown.operation',
            sourceEntityRef: 'travel.TripShareSnapshot:share-1@1',
          ),
          receipt: receipt,
        ),
        throwsA(isA<PostPublicationContinuationRejectedException>()),
      );
    },
  );

  test('registry refuses duplicate operation owners', () {
    expect(
      () => PostPublicationContinuationRegistry(
        <PostPublicationContinuationHandler>[
          _RecordingHandler(),
          _RecordingHandler(),
        ],
      ),
      throwsStateError,
    );
  });
}

PostPublicationReceipt _receipt() => PostPublicationReceipt(
  publishIntentId: 'publish-1',
  localDraftId: 'draft-1',
  postId: 'post-1',
  state: 'published',
  committedVersion: 1,
  acceptedAt: DateTime.utc(2026, 8, 2),
);

final class _RecordingHandler implements PostPublicationContinuationHandler {
  final List<CreateDraftPublicationContinuationRef> continuations =
      <CreateDraftPublicationContinuationRef>[];

  @override
  String get operationId => 'travel.content_link.put';

  @override
  Future<void> apply({
    required CreateDraftPublicationContinuationRef continuation,
    required PostPublicationReceipt receipt,
  }) async {
    continuations.add(continuation);
  }
}
