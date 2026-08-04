import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// 发图「上传 → 绑定 → 原子发布」端云契约桥测试。
///
/// 历史缺陷：本文件曾引用仓库中不存在的 Go 用例
/// `TestSubmitPostPublicationWithMediaContract`，`go test -run` 零匹配仍
/// exit 0，导致永绿零验证。修复后必须同时满足：
/// 1. 只允许引用真实存在的 Go api_integration 用例；
/// 2. 断言实际运行了目标用例（防零匹配假绿）。
void main() {
  test(
    'content-service media upload and atomic publication contract stays green',
    () async {
      const targetTests = <String>[
        // init → complete → processing-result → 发布时校验 ready+owner 并
        // 物化公开 slice（post_markdown_contract__api_integration_test.go）。
        'TestSubmitPostPublicationBindsReadyOwnedMedia',
        // 原子发布回执与 published 投影（post_crud_contract__api_integration_test.go）。
        'TestSubmitPostPublicationCreatesPublishedPost',
      ];
      final result = await Process.run(
        'go',
        <String>[
          'test',
          './services/content-service/tests/api_integration/content/post',
          '-run',
          '^(${targetTests.join('|')})\$',
          '-count=1',
          '-v',
        ],
        workingDirectory: '../quwoquan_service',
      );

      final combinedOutput = '${result.stdout}\n${result.stderr}';
      expect(result.exitCode, 0, reason: combinedOutput);
      expect(
        combinedOutput.contains('no tests to run'),
        isFalse,
        reason: 'go test 零匹配即假绿，目标用例必须真实存在:\n$combinedOutput',
      );
      for (final testName in targetTests) {
        expect(
          combinedOutput.contains('--- PASS: $testName'),
          isTrue,
          reason: '$testName 未实际运行或未通过:\n$combinedOutput',
        );
      }
    },
    timeout: const Timeout(Duration(minutes: 10)),
  );
}
