// raw SDK 默认 Alpha，在线制品显式使用 metadata 的 main_prod 入口。
import 'package:quwoquan_app/main_alpha.dart' as alpha_entrypoint;

Future<void> main() async {
  await alpha_entrypoint.main();
}
