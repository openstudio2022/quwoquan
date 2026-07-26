import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_homepage/homepage_introduction.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

final homepageIntroductionProvider =
    FutureProvider.family<HomepageIntroduction?, String>((ref, homepageId) {
      final repository = ref.watch(homepageIntroductionRepositoryProvider);
      return repository.getHomepageIntroduction(homepageId);
    });
