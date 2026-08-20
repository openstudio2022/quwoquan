/// Environment Patrol 的唯一 App 启动入口。
///
/// test host 的临时 wrapper 只会编译 canonical target 及其 imports；
/// Alpha/Beta/Gamma/Prod 始终启动同一套 production Remote composition。
library;

import 'package:patrol/patrol.dart';
import 'patrol_test_support.dart';

Future<void> launchEnvironmentPatrolApp(PatrolIntegrationTester $) =>
    launchPatrolAppOnce($);
