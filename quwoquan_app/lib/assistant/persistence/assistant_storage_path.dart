import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Android 和 iOS 在不同根目录下共享同一助手持久化子目录。
const String personalAssistantSubdir = '.personal_assistant';

Future<String> getPersonalAssistantStoragePath(String filename) async {
  final dir = await getApplicationDocumentsDirectory();
  var basePath = dir.path;
  if (basePath.endsWith('app_flutter')) {
    basePath = Directory(basePath).parent.path;
  }
  return '$basePath/$personalAssistantSubdir/$filename';
}
