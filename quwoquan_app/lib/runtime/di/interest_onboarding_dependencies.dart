import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_onboarding_interest_writer.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/secure_interest_onboarding_draft_store.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/interest_onboarding.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';

final interestOnboardingDraftStoreProvider =
    Provider<InterestOnboardingDraftStore>(
      (ref) => const SecureInterestOnboardingDraftStore(),
    );

final interestOnboardingCoordinatorProvider =
    Provider<InterestOnboardingCoordinator>((ref) {
      return InterestOnboardingCoordinator(
        draftStore: ref.watch(interestOnboardingDraftStoreProvider),
        writer: BehaviorOnboardingInterestWriter(
          ref.watch(behaviorRepositoryProvider),
        ),
      );
    });
