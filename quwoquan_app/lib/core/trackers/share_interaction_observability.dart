import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';

class ShareInteractionEventNames {
  static const String view = 'share_interaction_view';
  static const String directionChange = 'share_direction_change';
  static const String impression = 'share_interaction_impression';
  static const String open = 'share_interaction_open';
  static const String actorOpen = 'share_actor_open';
  static const String impactOpen = 'share_impact_open';
  static const String refresh = 'share_refresh';
  static const String loadMore = 'share_load_more';

  const ShareInteractionEventNames._();
}

class ShareInteractionObservability {
  ShareInteractionObservability(this._analytics);

  static const String source = 'profile_interaction_share';
  final AnalyticsService _analytics;

  void track({
    required String eventName,
    required String subAccountId,
    required ShareInteractionDirection direction,
    ShareInteractionItem? item,
    String? result,
    bool? cacheHit,
    int? itemCount,
  }) {
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'share_interaction',
          eventName: eventName,
          properties: <String, dynamic>{
            'subAccountId': subAccountId,
            'direction': direction.name,
            'interactionId': ?item?.interactionId,
            'targetKind': ?item?.targetKind.name,
            'targetId': ?item?.targetContentId,
            'outboundShareEventId': ?item?.outboundShareEventId,
            'source': source,
            'result': ?result,
            'cacheHit': ?cacheHit,
            'itemCount': ?itemCount,
          },
        ),
      ),
    );
  }
}

final shareInteractionObservabilityProvider =
    Provider<ShareInteractionObservability>(
      (ref) => ShareInteractionObservability(ref.read(analyticsProvider)),
    );
