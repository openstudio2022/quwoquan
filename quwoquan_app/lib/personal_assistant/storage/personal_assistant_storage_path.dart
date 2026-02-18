import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// 个人私人助手存储路径：Android 为应用包目录（去掉 app_flutter），iOS 为应用沙箱目录，
/// 两者在各自根目录下使用相同的子目录 [personalAssistantSubdir]，仅根目录不同。
const String personalAssistantSubdir = '.personal_assistant';

/// 返回应用根目录下的「个人私人助手」子目录中的文件路径。
/// - Android：先取 [getApplicationDocumentsDirectory]，若路径以 `app_flutter` 结尾则用其父目录作为应用包目录。
/// - iOS：使用应用 Documents 目录，其下为 [personalAssistantSubdir]。
/// 子目录名两端一致，仅根目录因平台不同而不同。
Future<String> getPersonalAssistantStoragePath(String filename) async {
  final dir = await getApplicationDocumentsDirectory();
  var basePath = dir.path;
  if (basePath.endsWith('app_flutter')) {
    basePath = Directory(basePath).parent.path;
  }
  return '$basePath/$personalAssistantSubdir/$filename';
}
