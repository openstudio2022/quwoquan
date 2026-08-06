// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_run_remote_api_harness.dart';

void main() {
  test('找私助 beta 权威来源 API integration', () async {
    final harness = await AssistantRunRemoteApiHarness.fromEnvironment(
      allowedEnvironments: const {CloudEnvironment.beta},
    );
    addTearDown(harness.close);

    for (final promptCase in _authorityPromptCases) {
      final result = await _runPromptCase(harness, promptCase);
      expect(result.run.status, 'completed', reason: promptCase.name);
      expect(result.snapshot.failure, isNull, reason: promptCase.name);
      expect(result.answer, isNotEmpty, reason: promptCase.name);
      expect(
        result.answer.length,
        greaterThanOrEqualTo(120),
        reason: promptCase.name,
      );
      expect(
        result.snapshot.processes.any(
          (process) => process.summary.trim().isNotEmpty,
        ),
        isTrue,
        reason: promptCase.name,
      );
      expect(
        result.acceptedReferences.length,
        greaterThanOrEqualTo(promptCase.minimumReferenceCount),
        reason: promptCase.name,
      );
      if (promptCase.requireKnowledgeSourcesSection) {
        expect(result.answer, contains('知识来源'), reason: promptCase.name);
      }
      for (final keyword in promptCase.expectedKeywords) {
        expect(result.answer, contains(keyword), reason: promptCase.name);
      }
      final hosts = <String>{};
      for (final reference in result.acceptedReferences) {
        final uri = Uri.tryParse(reference.destination.url ?? '');
        final host = (uri?.host ?? '').toLowerCase();
        expect(
          uri?.scheme,
          'https',
          reason: '${promptCase.name} source scheme',
        );
        expect(host, isNotEmpty, reason: '${promptCase.name} missing host');
        hosts.add(host);
      }
      expect(
        hosts.length,
        greaterThanOrEqualTo(promptCase.minimumDistinctHosts),
        reason: '${promptCase.name} distinct hosts=$hosts',
      );
    }
  });
}

final class _AuthorityPromptCase {
  const _AuthorityPromptCase({
    required this.name,
    required this.prompt,
    required this.expectedKeywords,
  });

  final String name;
  final String prompt;
  final List<String> expectedKeywords;
  final int minimumReferenceCount = 2;
  final int minimumDistinctHosts = 1;
  final bool requireKnowledgeSourcesSection = true;
}

const _authorityPromptCases = <_AuthorityPromptCase>[
  _AuthorityPromptCase(
    name: '生产式AI资源清单',
    prompt:
        '假如你是位资深运营规划架构师，现在需要创建一个生产式AI应用，需要购买哪些云资源，基于性价比考虑，请给出具体的资源清单列表，要有具体的规格和价格信息。请优先检索权威/官方资料，并标注知识来源；如有必要，可以引用多家官方资料做对比。',
    expectedKeywords: <String>['规格', '价格'],
  ),
  _AuthorityPromptCase(
    name: '奇迹MU配置推荐',
    prompt:
        '我打算和朋友一起玩的游戏是奇迹mus20，给我推荐一套云上配置，人数最多8人。请基于权威资料给出服务器规格、网络与计费建议，并标注知识来源。',
    expectedKeywords: <String>['云服务器', '带宽'],
  ),
  _AuthorityPromptCase(
    name: '云桌面按需计费关机',
    prompt:
        '你好，我想问下云桌面的按需计费问题，假如云桌面主机关机的情况下，还会计费吗？如果不同厂商官方规则有差异，可以一起对比说明，并标注知识来源。',
    expectedKeywords: <String>['关机', '计费'],
  ),
  _AuthorityPromptCase(
    name: '模型调试学习规划',
    prompt: '我是一个开发者，想学习打模型调试，请帮我规划一个合适的云服务，并提供一个购买指引。请优先使用权威资料，并标注知识来源。',
    expectedKeywords: <String>['模型', '购买'],
  ),
];

Future<AssistantRemoteRunResult> _runPromptCase(
  AssistantRunRemoteApiHarness harness,
  _AuthorityPromptCase promptCase,
) async {
  final first = await harness.execute(promptCase.prompt);
  final retryNeeded =
      first.snapshot.failure != null ||
      first.answer.isEmpty ||
      first.acceptedReferences.length < promptCase.minimumReferenceCount;
  if (!retryNeeded) return first;
  final retry = await harness.execute(promptCase.prompt);
  return _score(retry) > _score(first) ? retry : first;
}

int _score(AssistantRemoteRunResult result) {
  var total = result.snapshot.failure == null ? 10 : 0;
  total += result.acceptedReferences.length * 3;
  total += result.answer.isNotEmpty ? 2 : 0;
  total += result.answer.length ~/ 80;
  return total;
}
