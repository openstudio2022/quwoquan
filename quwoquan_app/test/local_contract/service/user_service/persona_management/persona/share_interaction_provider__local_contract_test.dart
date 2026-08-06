// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-005
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-007
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_capabilities.dart';
import 'package:quwoquan_app/runtime/di/profile_interaction_activity_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('received/initiated 双桶独立缓存并在分身切换时清空', () async {
    final repository = _ShareRepository.immediate();
    final container = ProviderContainer(
      overrides: [
        profileInteractionQueryFacetProvider.overrideWithValue(repository),
        profileInteractionReadFactAppendFacetProvider.overrideWithValue(
          repository,
        ),
        authSessionControllerProvider.overrideWith(_TestAuthController.new),
      ],
    );
    addTearDown(container.dispose);

    const receivedKey = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.received,
    );
    const initiatedKey = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.initiated,
    );
    container.read(shareInteractionStateProvider(receivedKey));
    container.read(shareInteractionStateProvider(initiatedKey));
    await pumpEventQueue();

    expect(
      container
          .read(shareInteractionStateProvider(receivedKey))
          .items
          .single
          .direction,
      ShareInteractionDirection.received,
    );
    expect(
      container
          .read(shareInteractionStateProvider(initiatedKey))
          .items
          .single
          .direction,
      ShareInteractionDirection.initiated,
    );
    container
        .read(shareInteractionControllerProvider(receivedKey))
        .saveScrollOffset(280);
    container
        .read(shareInteractionControllerProvider(initiatedKey))
        .saveScrollOffset(640);
    expect(
      container.read(shareInteractionStateProvider(receivedKey)).scrollOffset,
      280,
    );
    expect(
      container.read(shareInteractionStateProvider(initiatedKey)).scrollOffset,
      640,
    );

    (container.read(authSessionControllerProvider.notifier)
            as _TestAuthController)
        .activate('persona-b');
    await pumpEventQueue();
    expect(
      container.read(shareInteractionStateProvider(receivedKey)).items,
      isEmpty,
    );
    expect(
      container.read(shareInteractionStateProvider(initiatedKey)).items,
      isEmpty,
    );
  });

  test('旧 generation 完成后不能覆盖新刷新结果', () async {
    final repository = _ShareRepository.deferred();
    final container = ProviderContainer(
      overrides: [
        profileInteractionQueryFacetProvider.overrideWithValue(repository),
        profileInteractionReadFactAppendFacetProvider.overrideWithValue(
          repository,
        ),
        authSessionControllerProvider.overrideWith(_TestAuthController.new),
      ],
    );
    addTearDown(container.dispose);
    const key = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.received,
    );
    container.read(shareInteractionStateProvider(key));
    await pumpEventQueue();
    expect(repository.pending, hasLength(1));

    final refresh = container
        .read(shareInteractionControllerProvider(key))
        .refresh();
    await pumpEventQueue();
    expect(repository.pending, hasLength(2));
    repository.pending[1].complete(_page('new-result', 'received'));
    await refresh;
    repository.pending[0].complete(_page('old-result', 'received'));
    await pumpEventQueue();

    expect(
      container
          .read(shareInteractionStateProvider(key))
          .items
          .single
          .interactionId,
      'new-result',
    );
  });

  test('read fact 失败回滚乐观态且可重试', () async {
    final repository = _ShareRepository.immediate()..failWrites = true;
    final telemetry = _CapturingTelemetryRecorder();
    final container = ProviderContainer(
      overrides: [
        profileInteractionQueryFacetProvider.overrideWithValue(repository),
        profileInteractionReadFactAppendFacetProvider.overrideWithValue(
          repository,
        ),
        authSessionControllerProvider.overrideWith(_TestAuthController.new),
        journeyEventTrackerProvider.overrideWithValue(
          JourneyEventTracker(telemetryReporter: telemetry),
        ),
      ],
    );
    addTearDown(container.dispose);
    const key = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.received,
    );
    container.read(shareInteractionStateProvider(key));
    await pumpEventQueue();
    final notifier = container.read(shareInteractionControllerProvider(key));
    final interactionId = container
        .read(shareInteractionStateProvider(key))
        .items
        .single
        .interactionId;

    await notifier.markRead(interactionId);
    var state = container.read(shareInteractionStateProvider(key));
    expect(state.items.single.readAt, isNull);
    expect(state.error, isA<StateError>());

    repository.failWrites = false;
    await notifier.markRead(interactionId);
    state = container.read(shareInteractionStateProvider(key));
    expect(state.items.single.readAt, isNotNull);
    expect(repository.appendCalls, 2);
    expect(
      telemetry.payloads.map((payload) => payload.extensions['action']),
      <Object?>['mark_read', 'mark_read'],
    );
    expect(
      telemetry.payloads.map((payload) => payload.extensions['result']),
      <Object?>['failure', 'success'],
    );
  });
}

class _TestAuthController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'test-token',
    ownerId: 'owner-a',
    activePersonaId: 'persona-a',
  );

  void activate(String personaId) {
    state = state.copyWith(activePersonaId: personaId);
  }
}

class _ShareRepository
    implements
        ContentProfileInteractionQueryFacet,
        ContentProfileInteractionReadFactAppendFacet {
  _ShareRepository._(this._deferred);

  factory _ShareRepository.immediate() => _ShareRepository._(false);
  factory _ShareRepository.deferred() => _ShareRepository._(true);

  final bool _deferred;
  bool failWrites = false;
  int appendCalls = 0;
  final List<Completer<ProfileInteractionActivityPageSlice>> pending =
      <Completer<ProfileInteractionActivityPageSlice>>[];

  @override
  Future<ProfileInteractionActivityPageSlice> listActivities(
    ContentProfileInteractionPageQuery query, {
    required InteractionDirection direction,
  }) {
    if (!_deferred) {
      return Future.value(
        _page('share-${direction.wireName}', direction.wireName),
      );
    }
    final completer = Completer<ProfileInteractionActivityPageSlice>();
    pending.add(completer);
    return completer.future;
  }

  @override
  Future<ProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) async {
    appendCalls += 1;
    if (failWrites) {
      throw StateError('read fact unavailable');
    }
    return ProfileInteractionReadFactAck(
      factId: 'fact-${command.activityId}-${command.state.wireName}',
      activityId: command.activityId,
      state: command.state,
      occurredAt: DateTime.utc(2026, 7, 12),
      replayed: false,
    );
  }
}

final class _CapturingTelemetryRecorder implements AppTelemetryRecorder {
  final List<AppTelemetryPayload> payloads = <AppTelemetryPayload>[];

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    payloads.add(payload);
    return AppTelemetryRecordResult.accepted;
  }
}

ProfileInteractionActivityPageSlice _page(String id, String direction) {
  return ProfileInteractionActivityPageSlice(
    items: <ProfileInteractionActivityView>[
      ProfileInteractionActivityView(
        ownerPersonaId: 'persona-a',
        activityId: id,
        activityType: InteractionActivityType.share,
        direction: InteractionDirection.fromWire(
          direction,
          'ProfileInteractionActivityView.direction',
        ),
        sourceType: 'local_contract',
        sourceEventId: 'event-$id',
        sourceVersion: 1,
        viewerReactionVersion: 1,
        targetVersion: 1,
        active: true,
        commentKind: 'none',
        viewerReaction: CommentReactionType.none,
        actorPersonaId: 'actor',
        actorDisplayName: '山海来信',
        actorAvatarVersion: 1,
        targetPersonaId: 'persona-a',
        targetContentId: 'target',
        targetContentType: ContentType.image,
        targetContentSummary: '川西晨光',
        targetKind: 'post',
        targetAvailability: 'available',
        targetReplyCount: 0,
        displayPersonaId: 'actor',
        displayName: '山海来信',
        displayAvatarVersion: 1,
        primaryText: '转发互动',
        previewMediaKind: 'text',
        previewText: '川西晨光',
        previewUnavailable: false,
        filterKeys: const <String>['shares'],
        createdAt: DateTime.utc(2026, 7, 12),
        occurredAt: DateTime.utc(2026, 7, 12),
      ),
    ],
    hasMore: false,
  );
}
