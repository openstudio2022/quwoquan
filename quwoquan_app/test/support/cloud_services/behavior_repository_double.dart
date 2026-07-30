import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';

/// local_contract 对象级 BehaviorRepository 记录替身。
///
/// production composition 与 Patrol/UAT 不可达。
class MockBehaviorRepository extends BehaviorRepository {
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
        action: BehaviorAction.onboardingInterest,
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
