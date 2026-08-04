import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/content/content/post/application/interest_onboarding.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/infrastructure/local/onboarding/secure_interest_onboarding_draft_store.dart';

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
