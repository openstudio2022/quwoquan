// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-009
// readiness_case: profile_interaction_activity_view_list_profile_interaction_activities_received_app_api
// readiness_case: profile_interaction_activity_view_list_profile_interaction_activities_sent_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness owner;
  late ContentApiContractHarness actor;
  var ownerCreated = false;
  var actorCreated = false;

  setUpAll(() async {
    owner = await ContentApiContractHarness.create();
    ownerCreated = true;
    actor = await ContentApiContractHarness.create();
    actorCreated = true;
  });

  tearDownAll(() async {
    if (actorCreated) {
      await actor.close();
    }
    if (ownerCreated) {
      await owner.close();
    }
  });

  test('production profile interaction Remote 回读同一 comment 的收发投影', () async {
    final sequence = DateTime.now().microsecondsSinceEpoch;
    final ownerPersonaId = _activePersonaId(owner);
    final actorPersonaId = _activePersonaId(actor);
    final publication = await owner.publication.submitPostPublication(
      SubmitContentPostPublicationCommand(
        publishIntentId: 'profile-activity-post-$sequence',
        localDraftId: 'profile-activity-draft-$sequence',
        contentType: ContentType.micro,
        contentIdentity: ContentIdentity.moment,
        body: 'Profile interaction API contract post $sequence',
        visibility: Visibility.public,
      ),
    );
    final postId = publication.postId;
    String? commentId;

    try {
      final comment = await actor.withIdempotencyKey(
        'profile-activity-comment-$sequence',
        () => actor.comments.createComment(
          CreateContentCommentCommand(
            postId: postId,
            content: 'profile interaction comment $sequence',
          ),
        ),
      );
      commentId = comment.id;

      final received = await _pollActivity(
        owner,
        ContentProfileInteractionPageQuery(
          personaId: ownerPersonaId,
          type: InteractionActivityType.comment,
          limit: 20,
        ),
        direction: InteractionDirection.received,
        commentId: comment.id,
      );
      final sent = await _pollActivity(
        actor,
        ContentProfileInteractionPageQuery(
          personaId: actorPersonaId,
          type: InteractionActivityType.comment,
          limit: 20,
        ),
        direction: InteractionDirection.sent,
        commentId: comment.id,
      );

      expect(received.ownerPersonaId, ownerPersonaId);
      expect(received.direction, InteractionDirection.received);
      expect(received.activityType, InteractionActivityType.comment);
      expect(received.actorPersonaId, actorPersonaId);
      expect(received.targetPersonaId, ownerPersonaId);
      expect(received.targetContentId, postId);
      expect(received.commentId, comment.id);
      expect(received.active, isTrue);

      expect(sent.ownerPersonaId, actorPersonaId);
      expect(sent.direction, InteractionDirection.sent);
      expect(sent.activityType, InteractionActivityType.comment);
      expect(sent.actorPersonaId, actorPersonaId);
      expect(sent.targetPersonaId, ownerPersonaId);
      expect(sent.targetContentId, postId);
      expect(sent.commentId, comment.id);
      expect(sent.sourceEventId, received.sourceEventId);
      expect(sent.sourceVersion, received.sourceVersion);

      await actor.withIdempotencyKey(
        'profile-activity-comment-clean-$sequence',
        () => actor.comments.deleteComment(
          DeleteContentCommentCommand(postId: postId, commentId: comment.id),
        ),
      );
      commentId = null;
    } finally {
      if (commentId != null) {
        await actor.withIdempotencyKey(
          'profile-activity-comment-clean-$sequence',
          () => actor.comments.deleteComment(
            DeleteContentCommentCommand(postId: postId, commentId: commentId!),
          ),
        );
      }
      await owner.postDeletion.deletePost(
        postId: postId,
        idempotencyKey: 'profile-activity-post-clean-$sequence',
      );
    }
  });
}

String _activePersonaId(ContentApiContractHarness harness) {
  final personaId = harness.session.activePersona?.personaId.trim() ?? '';
  if (personaId.isEmpty) {
    throw StateError('Disposable account has no active persona');
  }
  return personaId;
}

Future<ProfileInteractionActivityView> _pollActivity(
  ContentApiContractHarness harness,
  ContentProfileInteractionPageQuery query, {
  required InteractionDirection direction,
  required String commentId,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (true) {
    final page = await harness.profileInteractions.listActivities(
      query,
      direction: direction,
    );
    for (final item in page.items) {
      if (item.commentId == commentId) {
        return item;
      }
    }
    if (DateTime.now().isAfter(deadline)) {
      throw StateError(
        'Timed out waiting for ${direction.wireName} profile activity',
      );
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
}
