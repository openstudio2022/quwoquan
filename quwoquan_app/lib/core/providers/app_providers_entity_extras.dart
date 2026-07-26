part of 'app_providers.dart';

/// production 恒为 Remote-only；alpha runner 与测试经 override 注入 mock 装配。
final homepageIntroductionRepositoryProvider =
    Provider<HomepageIntroductionRepository>((ref) {
      return HomepageIntroductionProjectionAdapter(
        query: ref.watch(_homepageQueryAdapterProvider),
      );
    });
