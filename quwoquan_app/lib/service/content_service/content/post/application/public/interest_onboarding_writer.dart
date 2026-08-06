abstract interface class ConfirmedOnboardingInterestWriter {
  Future<void> submit({
    required String clientEventId,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  });
}
