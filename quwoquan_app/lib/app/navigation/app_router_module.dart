import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/app_router.dart' deferred as impl;

bool _libraryLoaded = false;
Future<void>? _activeLoad;
Object? _lastLoadError;
StackTrace? _lastLoadStack;
int _loadAttempt = 0;
Future<void> Function() _libraryLoader = impl.loadLibrary;

/// 欢迎页完成前不得加载路由库，避免 Phase1/首帧拉入 80+ 页面 import 图。
bool get isAppRouterLibraryLoaded => _libraryLoaded;
int get appRouterLibraryLoadAttempt => _loadAttempt;
Object? get appRouterLibraryLastLoadError => _lastLoadError;
StackTrace? get appRouterLibraryLastLoadStack => _lastLoadStack;

/// 执行一条可观测、共享的 deferred Router 加载尝试。
///
/// `retry` 不重绘旧失败 future，而是建立新的 attempt；调用方必须自行对单次尝试施加
/// deadline，并在失效后进入安全 Shell。
Future<void> ensureAppRouterLibraryLoaded({bool retry = false}) async {
  if (_libraryLoaded) {
    return;
  }
  if (!retry && _activeLoad != null) {
    return _activeLoad!;
  }
  final attempt = ++_loadAttempt;
  _lastLoadError = null;
  _lastLoadStack = null;
  late final Future<void> load;
  load = _libraryLoader()
      .then((_) {
        if (attempt == _loadAttempt) {
          _libraryLoaded = true;
        }
      })
      .catchError((Object error, StackTrace stack) {
        if (attempt == _loadAttempt) {
          _lastLoadError = error;
          _lastLoadStack = stack;
        }
        throw error;
      })
      .whenComplete(() {
        if (identical(_activeLoad, load)) {
          _activeLoad = null;
        }
      });
  _activeLoad = load;
  return load;
}

/// 仅供 local_contract 隔离 deferred load 状态。
void resetAppRouterLibraryLoaderForTesting() {
  _libraryLoaded = false;
  _activeLoad = null;
  _lastLoadError = null;
  _lastLoadStack = null;
  _loadAttempt = 0;
  _libraryLoader = impl.loadLibrary;
}

@visibleForTesting
void overrideAppRouterLibraryLoaderForTesting(Future<void> Function() loader) {
  _libraryLoader = loader;
}

Provider<GoRouter> get deferredAppRouterProvider {
  assert(
    _libraryLoaded,
    'Call ensureAppRouterLibraryLoaded() before reading deferredAppRouterProvider',
  );
  return impl.appRouterProvider;
}
