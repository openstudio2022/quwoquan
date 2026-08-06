// 生产/发布用入口：production composition 本身只装配 Remote ports。
import 'package:quwoquan_app/runtime/shell/startup/app_bootstrap.dart';

Future<void> main() async {
  await runQuwoquanApp();
}
