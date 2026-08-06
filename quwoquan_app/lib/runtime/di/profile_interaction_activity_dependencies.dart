import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_capabilities.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/share_interaction_observability.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/share_interaction_provider.dart';

final shareInteractionStateProvider =
    Provider.family<ShareInteractionState, ShareInteractionBucketKey>((
      ref,
      key,
    ) {
      return ref.watch(shareInteractionProvider(key));
    });

final shareInteractionControllerProvider =
    Provider.family<ShareInteractionController, ShareInteractionBucketKey>((
      ref,
      key,
    ) {
      return ref.watch(shareInteractionProvider(key).notifier);
    });

final shareInteractionTelemetryProvider = Provider<ShareInteractionTelemetry>((
  ref,
) {
  return ref.watch(shareInteractionObservabilityProvider);
});
