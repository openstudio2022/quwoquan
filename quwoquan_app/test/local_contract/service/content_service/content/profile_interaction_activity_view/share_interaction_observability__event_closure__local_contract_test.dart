// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-008
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-008.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-008.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-008.t3
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/share_interaction_observability.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_capabilities.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';

void main() {
  // GWT-008.t1：8 个事件一个不多一个不少。
  // 逐个点名而不是只数个数：改名同时补一个新名字会让计数不变，这里会指名道姓地失败。
  test('转发列表恰好上报 8 个具名事件', () {
    const declared = <String>[
      ShareInteractionEventNames.view,
      ShareInteractionEventNames.directionChange,
      ShareInteractionEventNames.impression,
      ShareInteractionEventNames.open,
      ShareInteractionEventNames.actorOpen,
      ShareInteractionEventNames.impactOpen,
      ShareInteractionEventNames.refresh,
      ShareInteractionEventNames.loadMore,
    ];
    expect(declared.toSet(), hasLength(8), reason: '事件名不得重复');
    expect(declared, <String>[
      'share_interaction_view',
      'share_direction_change',
      'share_interaction_impression',
      'share_interaction_open',
      'share_actor_open',
      'share_impact_open',
      'share_refresh',
      'share_load_more',
    ]);

    final list = File(
      '${_repositoryRoot()}/quwoquan_app/lib/service/user_service/persona_management/persona/presentation/share_interaction/share_interaction_list.dart',
    ).readAsStringSync();
    for (final name in <String>[
      'view',
      'directionChange',
      'impression',
      'open',
      'actorOpen',
      'impactOpen',
      'refresh',
      'loadMore',
    ]) {
      expect(
        list,
        contains('ShareInteractionEventNames.$name'),
        reason: '$name 已声明却没有任何触发点，等于事件闭环缺一环',
      );
    }
  });

  // GWT-008.t2：公共参数逐项在场，可选项缺席时不落成空串。
  test('每个事件都带齐七项公共参数', () {
    final analytics = _CapturingAnalytics();
    final telemetry = ShareInteractionObservability(analytics);
    telemetry.track(
      eventName: ShareInteractionEventNames.open,
      personaId: 'persona-a',
      direction: ShareInteractionDirection.received,
      item: _item(),
    );

    final event = analytics.events.single;
    expect(event.eventType, 'share_interaction');
    expect(event.eventName, 'share_interaction_open');
    expect(event.properties['personaId'], 'persona-a');
    expect(event.properties['direction'], 'received');
    expect(event.properties['interactionId'], 'share-1');
    expect(event.properties['targetKind'], 'record');
    expect(event.properties['targetId'], 'target-content');
    expect(event.properties['outboundShareEventId'], 'outbound-1');
    expect(event.properties['source'], 'profile_interaction_share');

    analytics.events.clear();
    telemetry.track(
      eventName: ShareInteractionEventNames.refresh,
      personaId: 'persona-a',
      direction: ShareInteractionDirection.initiated,
    );
    final itemless = analytics.events.single;
    expect(itemless.properties['personaId'], 'persona-a');
    expect(itemless.properties['direction'], 'initiated');
    expect(itemless.properties['source'], 'profile_interaction_share');
    for (final optional in <String>[
      'interactionId',
      'targetKind',
      'targetId',
      'outboundShareEventId',
      'result',
      'cacheHit',
      'itemCount',
    ]) {
      expect(
        itemless.properties.containsKey(optional),
        isFalse,
        reason: '$optional 缺席时必须整键不在场，不得塌陷成空串或 0',
      );
    }
  });

  // GWT-008.t3：浏览列表与执行一次转发是两件事，事件不得互相顶替。
  test('列表浏览事件不复用执行转发行为链路', () {
    final root = _repositoryRoot();
    for (final path in <String>[
      'quwoquan_app/lib/service/content_service/content/post/presentation/content_share_actions.dart',
      'quwoquan_app/lib/service/content_service/content/post/presentation/content_share_sheet.dart',
    ]) {
      final file = File('$root/$path');
      if (!file.existsSync()) continue;
      final source = file.readAsStringSync();
      expect(
        source,
        isNot(contains('ShareInteractionEventNames')),
        reason: '$path 是执行转发链路，不得复用列表浏览事件',
      );
      expect(source, isNot(contains('profile_interaction_share')));
    }

    final observability = File(
      '$root/quwoquan_app/lib/service/content_service/content/profile_interaction_activity_view/application/share_interaction_observability.dart',
    ).readAsStringSync();
    expect(
      RegExp("eventType: 'share_interaction'").allMatches(observability).length,
      1,
      reason: '列表侧只有一个事件类型出口，不得分叉出第二个',
    );
  });
}

String _repositoryRoot() {
  final cwd = Directory.current;
  return cwd.path.endsWith('quwoquan_app') ? cwd.parent.path : cwd.path;
}

ShareInteractionItem _item() {
  return ShareInteractionItem(
    interactionId: 'share-1',
    direction: ShareInteractionDirection.received,
    displayPersonaId: 'actor',
    displayName: '山海来信',
    displayAvatarUrl: '',
    targetPersonaId: 'persona-a',
    targetContentId: 'target-content',
    targetContentType: 'image',
    targetSummary: '川西晨光',
    targetKind: ShareTargetKind.record,
    targetAvailability: ShareTargetAvailability.active,
    targetReplyCount: 0,
    previewKind: SharePreviewKind.text,
    previewImageUrl: '',
    previewText: '川西晨光',
    outboundShareEventId: 'outbound-1',
    shareText: '读完想再走一次。',
    impactPrimaryText: '带来 3 次新浏览',
    impactDeepLink: 'myIntersections',
    occurredAt: DateTime.utc(2026, 7, 12),
  );
}

/// 只截住 `trackEvent` 的入参，不改上报链路的其余行为：这里要判的是
/// observability 组装出的公共参数，而不是 telemetry 出站投影。
class _CapturingAnalytics extends AnalyticsService {
  _CapturingAnalytics() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}
