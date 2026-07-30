// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-005
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-007
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';
import 'package:quwoquan_app/ui/user/providers/share_interaction_provider.dart';
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
    container.read(shareInteractionProvider(key));
    await pumpEventQueue();
    final notifier = container.read(shareInteractionProvider(key).notifier);
    final interactionId = container
        .read(shareInteractionProvider(key))
        .items
        .single
        .interactionId;

    await notifier.markRead(interactionId);
    var state = container.read(shareInteractionProvider(key));
    expect(state.items.single.readAt, isNull);
    expect(state.error, isA<StateError>());

    repository.failWrites = false;
    await notifier.markRead(interactionId);
    state = container.read(shareInteractionProvider(key));
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
  final List<Completer<ContentProfileInteractionPage>> pending =
      <Completer<ContentProfileInteractionPage>>[];

  @override
  Future<ContentProfileInteractionPage> listActivities(
    ContentProfileInteractionPageQuery query, {
    required ContentProfileInteractionDirection direction,
  }) {
    if (!_deferred) {
      return Future.value(
        _page('share-${direction.wireValue}', direction.wireValue),
      );
    }
    final completer = Completer<ContentProfileInteractionPage>();
    pending.add(completer);
    return completer.future;
  }

  @override
  Future<ContentProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) async {
    appendCalls += 1;
    if (failWrites) {
      throw StateError('read fact unavailable');
    }
    return ContentProfileInteractionReadFactAck(
      factId: 'fact-${command.activityId}-${command.state.wireValue}',
      activityId: command.activityId,
      state: command.state.wireValue,
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

ContentProfileInteractionPage _page(String id, String direction) {
  return ContentProfileInteractionPage(
    items: <ContentProfileInteractionActivity>[
      ContentProfileInteractionActivity(
        activityId: id,
        activityType: 'share',
        direction: direction,
        actorPersonaId: 'actor',
        actorDisplayName: '山海来信',
        targetPersonaId: 'persona-a',
        targetContentId: 'target',
        targetContentType: 'image',
        targetContentSummary: '川西晨光',
        displayPersonaId: 'actor',
        displayName: '山海来信',
        primaryText: '转发互动',
        previewMediaKind: 'text',
        previewText: '川西晨光',
        filterKeys: const <String>['shares'],
        createdAt: DateTime.utc(2026, 7, 12),
        occurredAt: DateTime.utc(2026, 7, 12),
      ),
    ],
  );
}
