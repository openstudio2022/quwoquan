// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-004
// readiness_case: profile_interaction_read_fact_append_profile_interaction_read_fact_app_api

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

  test('production read-fact Remote 幂等追加 seen/read 并回读单调投影', () async {
    final sequence = DateTime.now().microsecondsSinceEpoch;
    final ownerPersonaId = _activePersonaId(owner);
    final publication = await owner.publication.submitPostPublication(
      SubmitContentPostPublicationCommand(
        publishIntentId: 'profile-read-post-$sequence',
        localDraftId: 'profile-read-draft-$sequence',
        contentType: ContentType.micro,
        contentIdentity: ContentIdentity.moment,
        body: 'Profile read API contract post $sequence',
        visibility: Visibility.public,
      ),
    );
    final postId = publication.postId;
    String? commentId;

    try {
      final comment = await actor.withIdempotencyKey(
        'profile-read-comment-$sequence',
        () => actor.comments.createComment(
          CreateContentCommentCommand(
            postId: postId,
            content: 'profile read target $sequence',
          ),
        ),
      );
      commentId = comment.id;
      final activity = await _pollActivity(
        owner,
        ownerPersonaId,
        comment.id,
        requireReadAt: false,
      );

      final seenCommand = AppendContentProfileInteractionReadFactCommand(
        personaId: ownerPersonaId,
        activityId: activity.activityId,
        state: ProfileInteractionReadState.seen,
      );
      final seen = await owner.profileInteractionReads.appendReadFact(
        seenCommand,
      );
      final seenReplay = await owner.profileInteractionReads.appendReadFact(
        seenCommand,
      );
      expect(seen.activityId, activity.activityId);
      expect(seen.state, ProfileInteractionReadState.seen);
      expect(seen.replayed, isFalse);
      expect(seenReplay.factId, seen.factId);
      expect(seenReplay.activityId, seen.activityId);
      expect(seenReplay.replayed, isTrue);

      final readCommand = AppendContentProfileInteractionReadFactCommand(
        personaId: ownerPersonaId,
        activityId: activity.activityId,
        state: ProfileInteractionReadState.read,
      );
      final read = await owner.profileInteractionReads.appendReadFact(
        readCommand,
      );
      final readReplay = await owner.profileInteractionReads.appendReadFact(
        readCommand,
      );
      expect(read.activityId, activity.activityId);
      expect(read.state, ProfileInteractionReadState.read);
      expect(read.replayed, isFalse);
      expect(readReplay.factId, read.factId);
      expect(readReplay.replayed, isTrue);

      final projected = await _pollActivity(
        owner,
        ownerPersonaId,
        comment.id,
        requireReadAt: true,
      );
      expect(projected.activityId, activity.activityId);
      expect(projected.seenAt, isNotNull);
      expect(projected.readAt, isNotNull);
      expect(projected.readAt!.isBefore(projected.seenAt!), isFalse);

      await actor.withIdempotencyKey(
        'profile-read-comment-clean-$sequence',
        () => actor.comments.deleteComment(
          DeleteContentCommentCommand(postId: postId, commentId: comment.id),
        ),
      );
      commentId = null;
    } finally {
      if (commentId != null) {
        await actor.withIdempotencyKey(
          'profile-read-comment-clean-$sequence',
          () => actor.comments.deleteComment(
            DeleteContentCommentCommand(postId: postId, commentId: commentId!),
          ),
        );
      }
      await owner.postDeletion.deletePost(
        postId: postId,
        idempotencyKey: 'profile-read-post-clean-$sequence',
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
  String ownerPersonaId,
  String commentId, {
  required bool requireReadAt,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (true) {
    final page = await harness.profileInteractions.listActivities(
      ContentProfileInteractionPageQuery(
        personaId: ownerPersonaId,
        type: InteractionActivityType.comment,
        limit: 20,
      ),
      direction: InteractionDirection.received,
    );
    for (final item in page.items) {
      if (item.commentId == commentId &&
          (!requireReadAt || item.readAt != null)) {
        return item;
      }
    }
    if (DateTime.now().isAfter(deadline)) {
      throw StateError('Timed out waiting for profile read projection');
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
}
