import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

enum AppDataSourceMode { mock, remote }

class AppDataSourceModeNotifier extends Notifier<AppDataSourceMode> {
  @override
  AppDataSourceMode build() {
    return resolveAppDataSourceModeForEnvironment(
      runtimeEnv: CloudRuntimeConfig.appRuntimeEnv,
      explicitDataSource: const String.fromEnvironment(
        'APP_DATA_SOURCE',
        defaultValue: '',
      ),
    );
  }

  void setMode(AppDataSourceMode mode) {
    state = resolveAppDataSourceModeForEnvironment(
      runtimeEnv: CloudRuntimeConfig.appRuntimeEnv,
      explicitDataSource: mode == AppDataSourceMode.remote ? 'remote' : 'mock',
    );
  }
}

@visibleForTesting
AppDataSourceMode resolveAppDataSourceModeForEnvironment({
  required String runtimeEnv,
  required String explicitDataSource,
}) {
  final env = runtimeEnv.trim();
  final dataSource = explicitDataSource.trim();

  if (env == 'alpha') {
    return AppDataSourceMode.mock;
  }
  if (env == 'beta' || env == 'gamma' || env == 'prod') {
    return AppDataSourceMode.remote;
  }
  throw StateError(
    'APP_RUNTIME_ENV must be alpha, beta, gamma, or prod; got "$env" '
    '(APP_DATA_SOURCE="$dataSource")',
  );
}

final appDataSourceModeProvider =
    NotifierProvider<AppDataSourceModeNotifier, AppDataSourceMode>(
      AppDataSourceModeNotifier.new,
    );

/// UI 只消费该派生能力位，不自行分支环境或数据源枚举。
final mockDataSourceActiveProvider = Provider<bool>((ref) {
  return ref.watch(appDataSourceModeProvider) == AppDataSourceMode.mock;
});
