// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/circle_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late CircleApiContractHarness circle;
  late ContentApiContractHarness content;
  var circleCreated = false;
  var contentCreated = false;

  setUpAll(() async {
    circle = await CircleApiContractHarness.create();
    circleCreated = true;
    await circle.loginDisposableAccount('post-placement-moderator');
    content = await ContentApiContractHarness.create();
    contentCreated = true;
  });

  tearDownAll(() async {
    if (contentCreated) {
      await content.close();
    }
    if (circleCreated) {
      await circle.close();
    }
  });

  test(
    'production placement Remote 消费真实 Post 投影并完成 place/pin/feature/remove',
    () async {
      final sequence = DateTime.now().microsecondsSinceEpoch;
      final createdCircle = await circle.withIdempotencyKey(
        'placement-circle-$sequence',
        () => circle.lifecycle.createCircle(
          CreateCircleCommand(
            name: 'Placement contract $sequence',
            category: 'community',
          ),
        ),
      );
      final publication = await content.publication.submitPostPublication(
        SubmitContentPostPublicationCommand(
          publishIntentId: 'placement-post-$sequence',
          localDraftId: 'placement-draft-$sequence',
          contentType: ContentType.micro,
          contentIdentity: ContentIdentity.moment,
          body: 'Circle placement API contract post $sequence',
          visibility: Visibility.public,
        ),
      );
      final circleId = createdCircle.circleId;
      final postId = publication.postId;
      String? placementId;

      try {
        final command = PlaceCirclePostCommand(
          circleId: circleId,
          postId: postId,
        );
        final placed = await _placeWhenPostProjectionIsReady(circle, command);
        placementId = placed.placementId;
        expect(placed.placementId, isNotEmpty);
        expect(placed.version, 1);
        expect(placed.state, 'active');
        expect(placed.idempotentReplay, isFalse);

        final placeReplay = await circle.postPlacement.placePost(command);
        expect(placeReplay.placementId, placed.placementId);
        expect(placeReplay.version, placed.version);
        expect(placeReplay.state, placed.state);
        expect(placeReplay.idempotentReplay, isTrue);

        final pinCommand = PinCirclePostCommand(
          circleId: circleId,
          placementId: placed.placementId,
          enabled: true,
        );
        final pinned = await circle.postPlacement.setPinned(pinCommand);
        final pinReplay = await circle.postPlacement.setPinned(pinCommand);
        expect(pinned.placementId, placed.placementId);
        expect(pinned.version, greaterThan(placed.version));
        expect(pinned.state, 'active');
        expect(pinned.idempotentReplay, isFalse);
        expect(pinReplay.version, pinned.version);
        expect(pinReplay.idempotentReplay, isTrue);

        final featureCommand = FeatureCirclePostCommand(
          circleId: circleId,
          placementId: placed.placementId,
          enabled: true,
        );
        final featured = await circle.postPlacement.setFeatured(featureCommand);
        final featureReplay = await circle.postPlacement.setFeatured(
          featureCommand,
        );
        expect(featured.placementId, placed.placementId);
        expect(featured.version, greaterThan(pinned.version));
        expect(featured.state, 'active');
        expect(featureReplay.version, featured.version);
        expect(featureReplay.idempotentReplay, isTrue);

        final removeCommand = RemoveCirclePostCommand(
          circleId: circleId,
          placementId: placed.placementId,
        );
        final removed = await circle.postPlacement.removePost(removeCommand);
        final removeReplay = await circle.postPlacement.removePost(
          removeCommand,
        );
        expect(removed.placementId, placed.placementId);
        expect(removed.version, greaterThan(featured.version));
        expect(removed.state, 'removed');
        expect(removed.idempotentReplay, isFalse);
        expect(removeReplay.version, removed.version);
        expect(removeReplay.state, 'removed');
        expect(removeReplay.idempotentReplay, isTrue);
        placementId = null;
      } finally {
        if (placementId != null) {
          await circle.postPlacement.removePost(
            RemoveCirclePostCommand(
              circleId: circleId,
              placementId: placementId,
            ),
          );
        }
        await content.postDeletion.deletePost(
          postId: postId,
          idempotencyKey: 'placement-post-clean-$sequence',
        );
        await circle.withIdempotencyKey(
          'placement-circle-clean-$sequence',
          () => circle.lifecycle.archiveCircle(
            ArchiveCircleCommand(circleId: circleId),
          ),
        );
      }
    },
  );
}

Future<CirclePostPlacementCommandResult> _placeWhenPostProjectionIsReady(
  CircleApiContractHarness harness,
  PlaceCirclePostCommand command,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (true) {
    try {
      return await harness.postPlacement.placePost(command);
    } on CloudException catch (error) {
      if (error.code != 'CIRCLE.USER.invalid_argument' ||
          DateTime.now().isAfter(deadline)) {
        rethrow;
      }
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
  }
}
