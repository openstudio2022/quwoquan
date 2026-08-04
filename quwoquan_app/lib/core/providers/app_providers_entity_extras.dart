import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers_client_sync.dart';
/// production 恒为 Remote-only；alpha runner 与测试经 override 注入 mock 装配。
final homepageIntroductionRepositoryProvider =
    Provider<HomepageIntroductionRepository>((ref) {
      return HomepageIntroductionProjectionAdapter(
        query: ref.watch(homepageQueryAdapterProvider),
      );
    });
