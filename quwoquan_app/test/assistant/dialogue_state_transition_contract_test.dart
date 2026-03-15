// 对话状态机转换契约测试
//
// 从 dialogue/state_transition_test_cases.json 加载测试用例，
// 对照 dialogue/state_transition_contract.json 中的 transitions 逐条验证。
// 不需要 LLM 调用，纯数据合法性验证。
import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  const skillsDir = 'assets/assistant/skills';

  final domainDirs = Directory(skillsDir)
      .listSync()
      .whereType<Directory>()
      .where(
        (d) => File(
          '${d.path}/dialogue/state_transition_contract.json',
        ).existsSync(),
      )
      .toList(growable: false);

  group('对话状态转换契约', () {
    for (final domainDir in domainDirs) {
      final domainId = domainDir.path.split('/').last;
      final contractFile = File(
        '${domainDir.path}/dialogue/state_transition_contract.json',
      );
      final testCasesFile = File(
        '${domainDir.path}/dialogue/state_transition_test_cases.json',
      );

      group('[$domainId]', () {
        test('契约文件结构合法', () {
          final contract =
              jsonDecode(contractFile.readAsStringSync())
                  as Map<String, dynamic>;
          expect(contract['contractId'], isNotEmpty, reason: 'contractId 不得为空');
          expect(
            contract['domainId'],
            equals(domainId),
            reason: 'contractId 中 domainId 应与目录名一致',
          );
          expect(contract['stateIds'], isA<List>(), reason: 'stateIds 必须是列表');
          expect(contract['events'], isA<List>(), reason: 'events 必须是列表');
          expect(
            contract['transitions'],
            isA<List>(),
            reason: 'transitions 必须是列表',
          );
          final transitions = contract['transitions'] as List;
          for (final t in transitions) {
            final transition = t as Map<String, dynamic>;
            expect(
              transition.containsKey('from') &&
                  transition.containsKey('event') &&
                  transition.containsKey('to'),
              isTrue,
              reason: 'transitions 每条必须包含 from/event/to',
            );
          }
        });

        if (testCasesFile.existsSync()) {
          test('测试用例全部命中契约', () {
            final contract =
                jsonDecode(contractFile.readAsStringSync())
                    as Map<String, dynamic>;
            final testCases =
                jsonDecode(testCasesFile.readAsStringSync())
                    as Map<String, dynamic>;
            final transitions = (contract['transitions'] as List)
                .cast<Map<String, dynamic>>();

            // 构建 from+event → to 索引
            final transitionIndex = <String, String>{};
            for (final t in transitions) {
              final key = '${t['from']}__${t['event']}';
              transitionIndex[key] = t['to'] as String;
            }

            final cases = (testCases['cases'] as List? ?? [])
                .cast<Map<String, dynamic>>();

            expect(
              cases,
              isNotEmpty,
              reason: 'state_transition_test_cases.json 不得为空',
            );

            for (final tc in cases) {
              final caseId = tc['caseId'] as String? ?? 'unknown';
              final from = tc['from'] as String;
              final event = tc['event'] as String;
              final expectTo = tc['expectTo'] as String;
              final key = '${from}__$event';
              final actualTo = transitionIndex[key];

              expect(
                actualTo,
                isNotNull,
                reason: '[$domainId][$caseId] 未找到转换: $from + $event',
              );
              expect(
                actualTo,
                equals(expectTo),
                reason: '[$domainId][$caseId] 期望转换到 $expectTo，契约中实际为 $actualTo',
              );
            }
          });
        } else {
          test('state_transition_test_cases.json 文件存在', () {
            expect(
              testCasesFile.existsSync(),
              isTrue,
              reason:
                  '[$domainId] 缺少 dialogue/state_transition_test_cases.json',
            );
          });
        }
      });
    }
  });
}
