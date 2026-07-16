import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('canonical 页面对象契约通过阻断门禁', () {
    final appRoot =
        File('scripts/runtime/verify_page_object_contract.py').existsSync()
        ? Directory.current
        : Directory('quwoquan_app');
    final gate = File(
      '${appRoot.path}/scripts/runtime/verify_page_object_contract.py',
    );

    expect(gate.existsSync(), isTrue, reason: '未找到页面对象契约门禁脚本');

    final result = Process.runSync('python3', <String>[
      'scripts/runtime/verify_page_object_contract.py',
    ], workingDirectory: appRoot.path);
    final output = '${result.stdout}${result.stderr}';

    expect(result.exitCode, 0, reason: output);
    expect(output, contains('page_object_contract: OK'));
  });
}
