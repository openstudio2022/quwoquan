import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/post/post_publication_status_reader.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/entry/providers/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/post_publication_task_section.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('发布任务区分待审核与失败，并提供对应恢复动作', (tester) async {
    String? retriedDraftId;
    String? editedDraftId;
    final createdAt = DateTime.utc(2026, 7, 20);
    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: PostPublicationTaskSection(
            intents: <LocalPostPublicationIntent>[
              _intent(
                draftId: 'draft-review',
                createdAt: createdAt,
                publicationState: ContentPostPublicationState.pendingReview,
                postId: 'post-review',
              ),
              _intent(
                draftId: 'draft-rejected',
                createdAt: createdAt,
                publicationState: ContentPostPublicationState.rejected,
                postId: 'post-rejected',
                blocked: true,
                blockReason: LocalPostPublicationBlockReason.rejected,
              ),
            ],
            onRetry: (intent) => retriedDraftId = intent.command.localDraftId,
            onEdit: (intent) => editedDraftId = intent.command.localDraftId,
            onRemove: (_) {},
          ),
        ),
      ),
    );

    expect(find.text(UITextConstants.publishTasksTitle), findsOneWidget);
    expect(
      find.text(UITextConstants.publishTaskPendingReviewStatus),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.publishTaskRejectedStatus),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('publication_task_retry_draft-review')),
    );
    expect(retriedDraftId, 'draft-review');

    await tester.tap(
      find.byKey(
        const ValueKey<String>('publication_task_edit_draft-rejected'),
      ),
    );
    expect(editedDraftId, 'draft-rejected');
  });
}

LocalPostPublicationIntent _intent({
  required String draftId,
  required DateTime createdAt,
  ContentPostPublicationState? publicationState,
  String? postId,
  bool blocked = false,
  LocalPostPublicationBlockReason? blockReason,
}) {
  return LocalPostPublicationIntent(
    command: SubmitContentPostPublicationCommand(
      publishIntentId: 'intent-$draftId',
      localDraftId: draftId,
      contentType: ContentPostType.micro,
      body: '发布任务正文 $draftId',
    ),
    authorPersonaId: 'persona-publication',
    circleIds: const <String>[],
    createdAt: createdAt,
    nextAttemptAt: createdAt,
    postId: postId,
    committedVersion: postId == null ? null : 1,
    acceptedAt: postId == null ? null : createdAt,
    publicationState: publicationState,
    blocked: blocked,
    blockReason: blockReason,
  );
}
