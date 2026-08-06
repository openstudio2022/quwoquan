import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('skill catalog decoder exposes one strict client projection', () {
    final catalog = decodeAssistantSkillCatalogListView(<String, Object?>{
      'items': <Object?>[
        <String, Object?>{
          'packageId': 'quwoquan.official.daily_assistant',
          'releaseDigest':
              'sha256:1111111111111111111111111111111111111111111111111111111111111111',
          'skillId': 'daily_assistant',
          'domainId': 'assistant',
          'displayName': '每日助手',
          'description': '管理每日计划',
          'catalogGroup': <String, Object?>{'id': 'life', 'displayText': '生活'},
          'requiresConsent': false,
          'requiredConsentScopes': <String>[],
          'consentScopeLabels': <Object?>[],
          'iconHint': 'checkmark',
          'targetAudiences': <Object?>[
            <String, Object?>{'id': 'all_users', 'displayText': '所有用户'},
          ],
          'dataUseSummary': '仅使用当前对话与公开信息',
          'examples': <Object?>[],
          'activationMode': 'hybrid',
          'surfaceKinds': <Object?>[
            <String, Object?>{'id': 'personal', 'displayText': '个人'},
          ],
          'configurationSchemaDigest':
              'sha256:2222222222222222222222222222222222222222222222222222222222222222',
          'setupTemplateRef': 'assistant.skill.setup.none',
          'configurationRequiredFields': <String>[],
        },
      ],
    });

    expect(catalog.items.single.skillId, 'daily_assistant');
    expect(catalog.items.single.requiresConsent, isFalse);
    expect(
      () => decodeAssistantSkillCatalogListView(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'skillId': 'daily_assistant',
            'displayName': '每日助手',
          },
        ],
      }),
      throwsFormatException,
    );
  });
}
