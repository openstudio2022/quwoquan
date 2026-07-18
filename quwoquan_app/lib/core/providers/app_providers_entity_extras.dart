part of 'app_providers.dart';

final homepageIntroductionRepositoryProvider =
    Provider<HomepageIntroductionRepository>((ref) {
      final mode = ref.watch(appDataSourceModeProvider);
      return cloudRepositoryImplForMode(
        mode,
        remote: () => RemoteHomepageIntroductionRepository(
          queryAdapter: ref.watch(_homepageQueryAdapterProvider),
        ),
        mock: () => const MockHomepageIntroductionRepository(),
      );
    });
