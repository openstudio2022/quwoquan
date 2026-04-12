import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/app_content/app_content_repository_mock.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

final appContentRepositoryProvider = Provider<AppContentRepository>((ref) {
  if (ref.watch(appDataSourceModeProvider) == AppDataSourceMode.remote) {
    return RemoteAppContentRepository();
  }
  return MockAppContentRepository();
});
