import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  group('user_phase_hints.json', () {
    late Map<String, dynamic> phases;

    setUpAll(() {
      final raw =
          jsonDecode(
                File(
                  'assets/assistant/config/user_phase_hints.json',
                ).readAsStringSync(),
              )
              as Map;
      phases = ((raw['phases'] as Map?) ?? const <String, dynamic>{})
          .cast<String, dynamic>();
    });

    test('保留 runtime 对齐所需的两段 phase key', () {
      expect(
        phases.keys,
        containsAll(const <String>['understanding', 'analyzing']),
      );
      expect(
        phases.containsKey('answering'),
        isFalse,
        reason: 'answering 已合并到 analyzing，不再作为独立 phase key',
      );
      expect(
        phases.containsKey('search'),
        isFalse,
        reason: '中间阶段的产品语义应保持为 analyzing，避免重新引入 runtime/config key 漂移',
      );
    });

    test('理解阶段提示保留叙事化和去机械化约束', () {
      final understanding =
          ((phases['understanding'] as Map?) ?? const <String, dynamic>{})
              .cast<String, dynamic>();
      final hint = (understanding['systemHint'] as String?) ?? '';

      expect(hint, contains('叙事自然语言'));
      expect(hint, contains('贴身助手'));
      expect(hint, contains('结构化标签'));
      expect(hint, contains('用户在意什么'));
      expect(hint, contains('接下来怎么确认'));
    });
  });
}
