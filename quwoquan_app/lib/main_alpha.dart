// Alpha 隔离制品入口；只有本 composition 可导入 canonical 离线 adapter。
import 'package:quwoquan_app/runtime/di/alpha_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_bootstrap.dart';

Future<void> main() async {
  configureAlphaDependencies();
  await runQuwoquanApp();
}
