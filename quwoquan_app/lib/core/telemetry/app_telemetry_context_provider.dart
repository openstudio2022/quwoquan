// ignore_for_file: prefer_initializing_formals

import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/widgets.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

final class AppTelemetryStaticContext {
  const AppTelemetryStaticContext({
    required this.deviceManufacturer,
    required this.deviceModel,
    required this.appVersion,
    required this.devicePlatform,
  });

  final String deviceManufacturer;
  final String deviceModel;
  final String appVersion;
  final String devicePlatform;
}

typedef AppTelemetryStaticContextLoader =
    Future<AppTelemetryStaticContext> Function();
typedef AppTelemetryConnectivityLoader =
    Future<List<ConnectivityResult>> Function();
typedef AppTelemetryConnectivityChanges = Stream<List<ConnectivityResult>>;

/// 导航、底栏、模态和异常处理共享的唯一当前页面上下文。
final class AppPageContextStore {
  AppPageContextStore._();

  static final AppPageContextStore instance = AppPageContextStore._();

  String _pageName = PageNames.appBootstrap;
  String _lastForegroundPageName = PageNames.appBootstrap;

  String get pageName => _pageName;

  bool updateFromLocation(String location) {
    final resolved = AppPages.pageNameFromLocation(location);
    if (resolved == null) return false;
    _pageName = resolved;
    return true;
  }

  void setPageName(String pageName) {
    final normalized = pageName.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(pageName, 'pageName', 'must not be empty');
    }
    _pageName = normalized;
    if (normalized != PageNames.appBackground) {
      _lastForegroundPageName = normalized;
    }
  }

  void markBackground() => _pageName = PageNames.appBackground;

  void markForeground() => _pageName = _lastForegroundPageName;

  void markBootstrap() => _pageName = PageNames.appBootstrap;
}

/// 缓存设备/版本静态信息并维护七值网络上下文。
final class AppTelemetryContextProvider with WidgetsBindingObserver {
  AppTelemetryContextProvider({
    AppTelemetryStaticContextLoader? staticContextLoader,
    Connectivity? connectivity,
    AppTelemetryConnectivityLoader? connectivityLoader,
    AppTelemetryConnectivityChanges? connectivityChanges,
    CellularNetworkProbe? cellularNetworkProbe,
    AppPageContextStore? pageContextStore,
  }) : _staticContextLoader = staticContextLoader ?? _loadPlatformStaticContext,
       _connectivity = connectivity ?? Connectivity(),
       _connectivityLoader = connectivityLoader,
       _connectivityChanges = connectivityChanges,
       _cellularNetworkProbe =
           cellularNetworkProbe ?? MethodChannelCellularNetworkProbe(),
       _pageContextStore = pageContextStore ?? AppPageContextStore.instance;

  static final AppTelemetryContextProvider instance =
      AppTelemetryContextProvider();

  final AppTelemetryStaticContextLoader _staticContextLoader;
  final Connectivity _connectivity;
  final AppTelemetryConnectivityLoader? _connectivityLoader;
  final AppTelemetryConnectivityChanges? _connectivityChanges;
  final CellularNetworkProbe _cellularNetworkProbe;
  final AppPageContextStore _pageContextStore;
  AppTelemetryStaticContext? _staticContext;
  Future<AppTelemetryStaticContext>? _staticLoad;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;
  final StreamController<String> _networkChanges =
      StreamController<String>.broadcast(sync: true);
  String _networkClass = 'none';
  int _networkRevision = 0;
  bool _observingLifecycle = false;

  bool get isInitialized => _staticContext != null;

  AppTelemetryStaticContext get staticContext =>
      _staticContext ??
      (throw StateError('AppTelemetryContextProvider.initialize not called'));

  String get networkClass => _networkClass;

  String get devicePlatform => staticContext.devicePlatform;

  Stream<String> get networkChanges => _networkChanges.stream;

  String get pageName => _pageContextStore.pageName;

  /// 冷启动同步占位：避免 `package_info` / 连通性探测阻塞 `runApp`。
  void bootstrapForColdStart({String appVersion = 'dev'}) {
    _staticContext ??= AppTelemetryStaticContext(
      deviceManufacturer: 'unknown',
      deviceModel: 'unknown',
      appVersion: appVersion,
      devicePlatform: platformWireName(currentAppPlatform),
    );
  }

  Future<void> initialize() async {
    bootstrapForColdStart();
    _staticLoad ??= _staticContextLoader();
    _staticContext = await _staticLoad;
    await _updateNetworkClass(
      await (_connectivityLoader?.call() ?? _connectivity.checkConnectivity()),
    );
    _connectivitySubscription ??=
        (_connectivityChanges ?? _connectivity.onConnectivityChanged).listen(
          (results) => unawaited(_updateNetworkClass(results)),
        );
    if (!_observingLifecycle) {
      WidgetsBinding.instance.addObserver(this);
      _observingLifecycle = true;
    }
  }

  Future<void> dispose() async {
    if (_observingLifecycle) {
      WidgetsBinding.instance.removeObserver(this);
      _observingLifecycle = false;
    }
    await _connectivitySubscription?.cancel();
    _connectivitySubscription = null;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.inactive:
        return;
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        _pageContextStore.markBackground();
        return;
      case AppLifecycleState.resumed:
        _pageContextStore.markForeground();
        return;
    }
  }

  static String resolveNetworkClass(
    Iterable<ConnectivityResult> results, {
    CellularNetworkGeneration cellularGeneration =
        CellularNetworkGeneration.unknown,
  }) {
    final values = results.toSet();
    final vpnOnly = values.remove(ConnectivityResult.vpn) && values.isEmpty;
    if (values.isEmpty) return vpnOnly ? 'other' : 'none';
    if (values.contains(ConnectivityResult.ethernet)) return 'ethernet';
    if (values.contains(ConnectivityResult.wifi)) return 'wifi';
    if (values.contains(ConnectivityResult.mobile)) {
      return switch (cellularGeneration) {
        CellularNetworkGeneration.g5 => '5g',
        CellularNetworkGeneration.g4 => '4g',
        CellularNetworkGeneration.unknown => 'mobile',
      };
    }
    if (values.contains(ConnectivityResult.bluetooth) ||
        values.contains(ConnectivityResult.satellite) ||
        values.contains(ConnectivityResult.other)) {
      return 'other';
    }
    return 'none';
  }

  Future<void> _updateNetworkClass(Iterable<ConnectivityResult> results) async {
    final snapshot = results.toList(growable: false);
    final revision = ++_networkRevision;
    var next = resolveNetworkClass(snapshot);
    if (next == 'mobile') {
      final generation = await _cellularNetworkProbe.readGeneration();
      if (revision != _networkRevision) return;
      next = resolveNetworkClass(snapshot, cellularGeneration: generation);
    }
    if (revision != _networkRevision) return;
    if (next == _networkClass) return;
    _networkClass = next;
    _networkChanges.add(next);
  }

  static Future<AppTelemetryStaticContext> _loadPlatformStaticContext() async {
    final device = await DeviceInfoPlugin().deviceInfo;
    final data = device.data;
    final package = await PackageInfo.fromPlatform();
    final manufacturer = _firstNonEmpty(<Object?>[
      data['manufacturer'],
      data['systemName'],
      data['browserName'],
      data['computerName'],
      data['name'],
      'unknown',
    ]);
    final model = _firstNonEmpty(<Object?>[
      data['model'],
      data['machine'],
      data['productName'],
      data['device'],
      data['platform'],
      'unknown',
    ]);
    final build = package.buildNumber.trim();
    return AppTelemetryStaticContext(
      deviceManufacturer: manufacturer,
      deviceModel: model,
      appVersion: build.isEmpty
          ? package.version.trim()
          : '${package.version.trim()}+$build',
      devicePlatform: platformWireName(currentAppPlatform),
    );
  }

  static String _firstNonEmpty(Iterable<Object?> values) {
    for (final value in values) {
      final normalized = value?.toString().trim() ?? '';
      if (normalized.isNotEmpty) return normalized;
    }
    return 'unknown';
  }
}
