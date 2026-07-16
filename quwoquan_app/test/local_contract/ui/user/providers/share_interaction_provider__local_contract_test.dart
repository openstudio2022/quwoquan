import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_interaction_activity_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';
import 'package:quwoquan_app/ui/user/providers/share_interaction_provider.dart';

void main() {
  test('received/initiated 双桶独立缓存并在分身切换时清空', () async {
    final repository = _ShareRepository.immediate();
    final container = ProviderContainer(
      overrides: [
        userProfileRepositoryProvider.overrideWithValue(repository),
        authSessionControllerProvider.overrideWith(_TestAuthController.new),
      ],
    );
    addTearDown(container.dispose);

    const receivedKey = ShareInteractionBucketKey(
      subAccountId: 'persona-a',
      direction: ShareInteractionDirection.received,
    );
    const initiatedKey = ShareInteractionBucketKey(
      subAccountId: 'persona-a',
      direction: ShareInteractionDirection.initiated,
    );
    container.read(shareInteractionProvider(receivedKey));
    container.read(shareInteractionProvider(initiatedKey));
    await pumpEventQueue();

    expect(
      container
          .read(shareInteractionProvider(receivedKey))
          .items
          .single
          .direction,
      ShareInteractionDirection.received,
    );
    expect(
      container
          .read(shareInteractionProvider(initiatedKey))
          .items
          .single
          .direction,
      ShareInteractionDirection.initiated,
    );
    container
        .read(shareInteractionProvider(receivedKey).notifier)
        .saveScrollOffset(280);
    container
        .read(shareInteractionProvider(initiatedKey).notifier)
        .saveScrollOffset(640);
    expect(
      container.read(shareInteractionProvider(receivedKey)).scrollOffset,
      280,
    );
    expect(
      container.read(shareInteractionProvider(initiatedKey)).scrollOffset,
      640,
    );

    (container.read(authSessionControllerProvider.notifier)
            as _TestAuthController)
        .activate('persona-b');
    await pumpEventQueue();
    expect(
      container.read(shareInteractionProvider(receivedKey)).items,
      isEmpty,
    );
    expect(
      container.read(shareInteractionProvider(initiatedKey)).items,
      isEmpty,
    );
  });

  test('旧 generation 完成后不能覆盖新刷新结果', () async {
    final repository = _ShareRepository.deferred();
    final container = ProviderContainer(
      overrides: [
        userProfileRepositoryProvider.overrideWithValue(repository),
        authSessionControllerProvider.overrideWith(_TestAuthController.new),
      ],
    );
    addTearDown(container.dispose);
    const key = ShareInteractionBucketKey(
      subAccountId: 'persona-a',
      direction: ShareInteractionDirection.received,
    );
    container.read(shareInteractionProvider(key));
    await pumpEventQueue();
    expect(repository.pending, hasLength(1));

    final refresh = container
        .read(shareInteractionProvider(key).notifier)
        .refresh();
    await pumpEventQueue();
    expect(repository.pending, hasLength(2));
    repository.pending[1].complete(_page('new-result', 'received'));
    await refresh;
    repository.pending[0].complete(_page('old-result', 'received'));
    await pumpEventQueue();

    expect(
      container.read(shareInteractionProvider(key)).items.single.interactionId,
      'new-result',
    );
  });
}

class _TestAuthController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'test-token',
    ownerId: 'owner-a',
    activeSubAccountId: 'persona-a',
  );

  void activate(String subAccountId) {
    state = state.copyWith(activeSubAccountId: subAccountId);
  }
}

class _ShareRepository extends MockUserProfileRepository {
  _ShareRepository._(this._deferred);

  factory _ShareRepository.immediate() => _ShareRepository._(false);
  factory _ShareRepository.deferred() => _ShareRepository._(true);

  final bool _deferred;
  final List<Completer<CursorPage<ProfileInteractionActivityViewData>>>
  pending = <Completer<CursorPage<ProfileInteractionActivityViewData>>>[];

  @override
  Future<CursorPage<ProfileInteractionActivityViewData>>
  listProfileShareInteractions(
    String subAccountId, {
    required String direction,
    String? cursor,
    int limit = 20,
  }) {
    if (!_deferred) {
      return Future.value(_page('share-$direction', direction));
    }
    final completer =
        Completer<CursorPage<ProfileInteractionActivityViewData>>();
    pending.add(completer);
    return completer.future;
  }
}

CursorPage<ProfileInteractionActivityViewData> _page(
  String id,
  String direction,
) {
  return CursorPage<ProfileInteractionActivityViewData>(
    items: <ProfileInteractionActivityViewData>[
      ProfileInteractionActivityViewData.fromProfileInteractionActivityWire(
        ProfileInteractionActivityWireDto(
          activityId: id,
          activityType: 'share',
          direction: direction,
          actorSubAccountId: 'actor',
          actorDisplayName: '山海来信',
          targetSubAccountId: 'persona-a',
          targetContentId: 'target',
          targetContentType: 'image',
          targetContentSummary: '川西晨光',
          displaySubAccountId: 'actor',
          displayName: '山海来信',
          primaryText: '转发互动',
          previewMediaKind: 'text',
          previewText: '川西晨光',
          filterKeys: const <String>['shares'],
          occurredAt: DateTime(2026, 7, 12),
        ),
      ),
    ],
  );
}
