/// Environment Patrol 的唯一 App 启动入口。
///
/// `patrol test -t <target>` 只会编译该 target 及其 imports，不能依赖同级
/// `patrol_test_main.dart` 的副作用。Alpha 仅在测试树中复用独立 runner 的完整
/// contract-fixture composition；Beta/Gamma 保持 production Remote composition。
library;

import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import '../cloud_services/repository_mock_reexports.dart'
    show buildAlphaCloudOverrides;

const _runtimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _dataSource = String.fromEnvironment('APP_DATA_SOURCE');

Future<void> launchEnvironmentPatrolApp(PatrolIntegrationTester $) {
  final alphaFixtureMode = _runtimeEnv == 'alpha' && _dataSource == 'mock';
  return launchPatrolAppOnce(
    $,
    providerScopeOverrides: alphaFixtureMode
        ? buildAlphaCloudOverrides()
        : const [],
  );
}
