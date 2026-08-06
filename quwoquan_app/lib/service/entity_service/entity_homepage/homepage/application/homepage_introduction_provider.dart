import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';

final homepageIntroductionProvider =
    FutureProvider.family<HomepageIntroduction?, String>((ref, homepageId) {
      final repository = ref.watch(homepageIntroductionRepositoryProvider);
      return repository.getHomepageIntroduction(homepageId);
    });
