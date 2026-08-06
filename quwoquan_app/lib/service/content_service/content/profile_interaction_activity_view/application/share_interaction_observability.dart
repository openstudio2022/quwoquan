import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_capabilities.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';

class ShareInteractionObservability implements ShareInteractionTelemetry {
  ShareInteractionObservability(this._analytics);

  final AnalyticsService _analytics;

  @override
  void track({
    required String eventName,
    required String personaId,
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
            'personaId': personaId,
            'direction': direction.name,
            'interactionId': ?item?.interactionId,
            'targetKind': ?item?.targetKind.name,
            'targetId': ?item?.targetContentId,
            'outboundShareEventId': ?item?.outboundShareEventId,
            'source': ShareInteractionTelemetry.source,
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
