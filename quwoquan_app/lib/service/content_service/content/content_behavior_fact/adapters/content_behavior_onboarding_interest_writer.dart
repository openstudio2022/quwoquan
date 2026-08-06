import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/interest_onboarding_writer.dart';

final class BehaviorOnboardingInterestWriter
    implements ConfirmedOnboardingInterestWriter {
  const BehaviorOnboardingInterestWriter(this._repository);

  final BehaviorRepository _repository;

  @override
  Future<void> submit({
    required String clientEventId,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  }) {
    return _repository.submitOnboardingInterest(
      clientEventId: clientEventId,
      taxonomyReleaseId: taxonomyReleaseId,
      tagRefs: tagRefs,
    );
  }
}
