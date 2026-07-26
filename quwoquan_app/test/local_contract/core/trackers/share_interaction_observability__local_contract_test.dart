// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-subaccount-homepage-unification/spec.md#gwt-008
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/core/trackers/share_interaction_observability.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';

void main() {
  test('转发互动 8 个事件走独立 interaction_share 语义且不污染 share 行为', () async {
    final analytics = _RecordingAnalytics();
    final tracker = ShareInteractionObservability(analytics);
    const events = <String>[
      ShareInteractionEventNames.view,
      ShareInteractionEventNames.directionChange,
      ShareInteractionEventNames.impression,
      ShareInteractionEventNames.open,
      ShareInteractionEventNames.actorOpen,
      ShareInteractionEventNames.impactOpen,
      ShareInteractionEventNames.refresh,
      ShareInteractionEventNames.loadMore,
    ];
    final item = _item();

    for (final eventName in events) {
      tracker.track(
        eventName: eventName,
        subAccountId: 'persona-a',
        direction: ShareInteractionDirection.received,
        item: item,
        result: 'success',
      );
    }
    await pumpEventQueue();

    expect(
      analytics.events.map((event) => event.eventName),
      containsAll(events),
    );
    expect(
      analytics.events.every(
        (event) =>
            event.eventType == 'share_interaction' &&
            event.eventType != 'share' &&
            event.properties['targetKind'] == 'record' &&
            event.properties['direction'] == 'received' &&
            event.properties['source'] == 'profile_interaction_share',
      ),
      isTrue,
    );
  });
}

class _RecordingAnalytics extends AnalyticsService {
  _RecordingAnalytics() : super.forTesting();

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];
}

ShareInteractionItem _item() {
  return ShareInteractionItem(
    interactionId: 'share-1',
    direction: ShareInteractionDirection.received,
    displaySubAccountId: 'actor',
    displayName: '山海来信',
    displayAvatarUrl: '',
    targetSubAccountId: 'persona-a',
    targetContentId: 'target',
    targetContentType: 'image',
    targetSummary: '川西晨光',
    targetKind: ShareTargetKind.record,
    targetAvailability: ShareTargetAvailability.active,
    targetReplyCount: 0,
    previewKind: SharePreviewKind.text,
    previewImageUrl: '',
    previewText: '川西晨光',
    outboundShareEventId: 'outbound-event-1',
    shareText: '',
    impactPrimaryText: '',
    impactDeepLink: '',
    occurredAt: DateTime(2026, 7, 12),
  );
}
