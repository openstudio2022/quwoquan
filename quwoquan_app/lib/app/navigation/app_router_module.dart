import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/app_router.dart' deferred as impl;

bool _libraryLoaded = false;

/// 欢迎页完成前不得加载路由库，避免 Phase1/首帧拉入 80+ 页面 import 图。
bool get isAppRouterLibraryLoaded => _libraryLoaded;

Future<void> ensureAppRouterLibraryLoaded() async {
  if (_libraryLoaded) {
    return;
  }
  await impl.loadLibrary();
  _libraryLoaded = true;
}

Provider<GoRouter> get deferredAppRouterProvider {
  assert(
    _libraryLoaded,
    'Call ensureAppRouterLibraryLoaded() before reading deferredAppRouterProvider',
  );
  return impl.appRouterProvider;
}
