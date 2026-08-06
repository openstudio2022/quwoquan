part of 'app_router.dart';

void _completeWelcome(WidgetRef ref) {
  ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
}

ReferralSource _referralSourceFromRoute(String value) {
  if (value.trim().isEmpty) {
    return ReferralSource.deepLink;
  }
  for (final source in ReferralSource.values) {
    if (source.value == value) {
      return source;
    }
  }
  return ReferralSource.deepLink;
}
