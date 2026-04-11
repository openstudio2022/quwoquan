import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// 助手元数据下共享 wire fixture（相对 `quwoquan_app` 运行目录：`../quwoquan_service/...`）。
String assistantMetadataFixturePath(String name) {
  final f = File('../quwoquan_service/contracts/metadata/assistant/test_fixtures/$name');
  expect(f.existsSync(), isTrue, reason: 'fixture 缺失: ${f.absolute.path}');
  return f.path;
}
