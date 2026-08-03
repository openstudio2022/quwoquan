import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';

import '../../../../support/cloud_services/assistant_facets_mock.dart';

void main() {
  test('mock skill catalog exposes creation assistant skill', () async {
    final repository = AlphaAssistantFacets();

    final skills = await repository.listSkillCatalog();

    expect(
      skills.any((skill) => skill.skillId == 'creation_assistant'),
      isTrue,
    );
  });

  test('creation assistance uses the canonical AssistantRun path', () async {
    final repository = AlphaAssistantFacets();
    await repository.createSkillSubscription(
      skillId: 'creation_assistant',
      domainId: 'content_creation',
      rawText: '发布前帮我整理标签和关联主页',
      clientRequestId: 'create-creation-assistant',
    );

    final response = await repository.startCreationRun(
      sessionId: 'session-creation-1',
      clientRequestId: 'run-creation-1',
      intent: AssistantCreationRunIntent(
        bodyDigest: '峨眉山旅行路线和摄影点整理',
        primaryHomepageId: 'homepage_sight_emeishan',
      ),
    );

    expect(response.runId, 'arn_mock_creation_run-creation-1');
    expect(response.sessionId, 'session-creation-1');
    expect(response.goal, contains('峨眉山旅行路线和摄影点整理'));
    expect(response.traceId, 'trace_mock_creation_run-creation-1');
  });
}
