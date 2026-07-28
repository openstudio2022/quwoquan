/// Environment Patrol 的唯一 App 启动入口。
///
/// `patrol test -t <target>` 只会编译该 target 及其 imports，不能依赖同级
/// `patrol_test_main.dart` 的副作用。Alpha/Beta/Gamma/Prod 始终启动同一套
/// production Remote composition。
library;

import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

Future<void> launchEnvironmentPatrolApp(PatrolIntegrationTester $) =>
    launchPatrolAppOnce($);
