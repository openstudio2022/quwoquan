import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_introduction_projection_adapter.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_introduction_repository.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart';

/// production 恒为 Remote-only；alpha runner 与测试经 override 注入 mock 装配。
final homepageIntroductionRepositoryProvider =
    Provider<HomepageIntroductionRepository>((ref) {
      return HomepageIntroductionProjectionAdapter(
        query: ref.watch(homepageIntroductionQueryProvider),
      );
    });
