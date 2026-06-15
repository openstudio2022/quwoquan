import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

void main() {
  test('mock skill catalog exposes creation assistant skill', () async {
    final repository = MockAssistantRepository();

    final skills = await repository.listSkillCatalog();

    expect(
      skills.any((skill) => skill.skillId == 'creation_assistant'),
      isTrue,
    );
  });

  test('creation suggest is unavailable before subscription', () async {
    final repository = MockAssistantRepository();

    final response = await repository.suggestCreationAssistance(
      request: const AssistantCreationSuggestRequest(
        bodyDigest: '峨眉山旅行路线和摄影点整理',
      ),
    );

    expect(response.available, isFalse);
    expect(response.unavailableReason, 'skill_not_enabled');
  });

  test(
    'creation suggest returns traceable suggestions after subscription',
    () async {
      final repository = MockAssistantRepository();
      await repository.createSkillSubscription(
        skillId: 'creation_assistant',
        domainId: 'content_creation',
        rawText: '发布前帮我整理标签和关联主页',
      );

      final response = await repository.suggestCreationAssistance(
        request: const AssistantCreationSuggestRequest(
          bodyDigest: '峨眉山旅行路线和摄影点整理',
          primaryHomepageId: 'homepage_sight_emeishan',
        ),
      );

      expect(response.available, isTrue);
      expect(response.suggestedTagRefs, contains('Topic/旅行'));
      expect(response.suggestedHomepages.single.id, 'homepage_sight_emeishan');
    },
  );
}
