// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/presentation/assistant_skill_center_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('mixed subscriptions and consent scopes keep independent facts', () {
    final item = AssistantSkillCenterItem(
      catalog: _catalog(),
      subscriptions: <SkillSubscriptionWire>[
        _subscription('sub-active', SkillSubscriptionStatus.active),
        _subscription('sub-paused', SkillSubscriptionStatus.paused),
      ],
      consent: const SkillConsent(
        id: 'consent-travel',
        accountId: 'account-1',
        skillId: 'travel_companion',
        grantedScopes: <String>[
          'assistant.learning.feedback_context.read',
          'assistant.memory.preferences.read',
        ],
        grantedAt: '2026-08-04T00:00:00Z',
        granted: true,
      ),
    );

    expect(item.hasSubscription, isTrue);
    expect(
      item.subscriptions.map((subscription) => subscription.subscriptionId),
      <String>['sub-active', 'sub-paused'],
    );
    expect(item.consentGranted, isTrue);
    expect(
      item.requiredConsentScopeLabels.map((scope) => scope.displayText),
      <String>['读取助手偏好'],
    );
    expect(
      item.optionalConsentScopeLabels.map((scope) => scope.displayText),
      <String>['使用脱敏的助手反馈摘要'],
    );
    expect(
      item.isConsentScopeGranted('assistant.learning.feedback_context.read'),
      isTrue,
    );
  });

  test('revoked consent remains visible but is not treated as granted', () {
    final item = AssistantSkillCenterItem(
      catalog: _catalog(),
      consent: const SkillConsent(
        id: 'consent-travel',
        accountId: 'account-1',
        skillId: 'travel_companion',
        grantedScopes: <String>['assistant.memory.preferences.read'],
        grantedAt: '2026-08-04T00:00:00Z',
        revokedAt: '2026-08-04T01:00:00Z',
        granted: false,
      ),
    );

    expect(item.consent, isNotNull);
    expect(item.consentGranted, isFalse);
    expect(
      item.isConsentScopeGranted('assistant.memory.preferences.read'),
      isFalse,
    );
  });
}

AssistantSkillCatalogItemView _catalog() => AssistantSkillCatalogItemView(
  packageId: 'quwoquan.official.travel_companion',
  skillId: 'travel_companion',
  domainId: 'travel',
  displayName: '贴身旅行管家',
  description: '一路计划，一路记录',
  releaseDigest:
      'sha256:4c9551c8a8f99035626cc42ce1ab1efbfb347b1a830bd822d8cf559960452f90',
  catalogGroup: const SkillCatalogSemanticLabel(
    id: 'travel',
    displayText: '旅行与共同出行',
  ),
  requiresConsent: true,
  requiredConsentScopes: const <String>['assistant.memory.preferences.read'],
  consentScopeLabels: const <SkillCatalogSemanticLabel>[
    SkillCatalogSemanticLabel(
      id: 'assistant.memory.preferences.read',
      displayText: '读取助手偏好',
    ),
    SkillCatalogSemanticLabel(
      id: 'assistant.learning.feedback_context.read',
      displayText: '使用脱敏的助手反馈摘要',
    ),
  ],
  targetAudiences: const <SkillCatalogSemanticLabel>[
    SkillCatalogSemanticLabel(id: 'trip_organizer', displayText: '自由行组织者'),
  ],
  dataUseSummary: '仅使用已授权的行程上下文',
  examples: const <ResolvedSkillExample>[],
  activationMode: SkillActivationMode.hybrid,
  surfaceKinds: const <SkillCatalogSemanticLabel>[
    SkillCatalogSemanticLabel(id: 'personal', displayText: '个人小趣'),
  ],
  configurationSchemaDigest:
      'sha256:68eb45adf8f46d2227ea1059c8fd29a7db84d4d8a9ec2281b125089b92e86b5c',
  setupTemplateRef: 'assistant.setup.travel_companion',
  configurationRequiredFields: const <String>[],
);

SkillSubscriptionWire _subscription(
  String id,
  SkillSubscriptionStatus status,
) => SkillSubscriptionWire(
  subscriptionId: id,
  version: 1,
  createdByUserId: 'account-1',
  skillId: 'travel_companion',
  status: status,
  createdAt: '2026-08-04T00:00:00Z',
  updatedAt: '2026-08-04T00:00:00Z',
);
