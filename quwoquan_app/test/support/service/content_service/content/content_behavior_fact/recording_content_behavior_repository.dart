import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show BehaviorEventType;

/// content_behavior_fact 对象级 local_contract 记录替身。
///
/// production composition 与 Patrol/UAT 不可达。
class RecordingContentBehaviorRepository extends BehaviorRepository {
  final List<BehaviorEvent> recorded = <BehaviorEvent>[];

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    recorded.addAll(events);
  }

  @override
  Future<void> submitOnboardingInterest({
    required String clientEventId,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  }) async {
    recorded.add(
      BehaviorEvent(
        contentId: '',
        action: BehaviorEventType.onboardingInterest,
        clientEventId: clientEventId,
        taxonomyReleaseId: taxonomyReleaseId,
        sourceSurface: 'interest_onboarding',
        tags: tagRefs,
      ),
    );
  }

  @override
  Future<void> clearPendingForLogout() async {
    recorded.clear();
  }
}
