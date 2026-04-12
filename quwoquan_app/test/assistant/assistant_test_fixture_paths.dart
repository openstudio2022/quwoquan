import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';

/// 助手元数据下共享 wire fixture（相对 `quwoquan_app` 运行目录：`../quwoquan_service/...`）。
String assistantMetadataFixturePath(String name) {
  final f = File('../quwoquan_service/contracts/metadata/assistant/test_fixtures/$name');
  expect(f.existsSync(), isTrue, reason: 'fixture 缺失: ${f.absolute.path}');
  return f.path;
}

/// 从 metadata `test_fixtures` 读取 JSON 并解析为 [RunArtifacts]（单测优先用此代替手写 `Map` 树）。
RunArtifacts assistantLoadRunArtifactsFixture(String name) {
  final path = assistantMetadataFixturePath(name);
  final map =
      jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
  return RunArtifacts.fromJson(map);
}

/// 从 metadata `test_fixtures` 读取 JSON 并解析为 [AssistantTurnOutput]。
AssistantTurnOutput assistantLoadAssistantTurnFixture(String name) {
  final path = assistantMetadataFixturePath(name);
  final map =
      jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
  return AssistantTurnOutput.fromJson(map);
}

/// 从 metadata `test_fixtures` 读取任意 JSON 对象（模型交互单测优先替代内联巨型 Map）。
Map<String, dynamic> assistantLoadJsonObjectFixture(String name) {
  final path = assistantMetadataFixturePath(name);
  return jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
}
