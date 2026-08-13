import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/application/skill_catalog_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../runtime/codec/canonical_digest_fixture.dart';

final class AssistantPrototypeSkillRow {
  const AssistantPrototypeSkillRow({
    required this.skillId,
    required this.name,
    this.description,
  });

  final String skillId;
  final String name;
  final String? description;
}

class InMemoryAssistantSkillCatalogFacet implements AssistantSkillCatalogFacet {
  static const List<AssistantPrototypeSkillRow> _prototypeSkills =
      <AssistantPrototypeSkillRow>[
        AssistantPrototypeSkillRow(
          skillId: 'summary',
          name: '总结',
          description: '每日/每周创作与社交汇总',
        ),
        AssistantPrototypeSkillRow(
          skillId: 'travel',
          name: '旅行',
          description: '出行攻略与目的地推荐',
        ),
        AssistantPrototypeSkillRow(
          skillId: 'reminder',
          name: '提醒',
          description: '关键信息与节日纪念日',
        ),
        AssistantPrototypeSkillRow(
          skillId: 'organize',
          name: '整理',
          description: '自动清理冗余信息与照片',
        ),
      ];

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = kAssistantSkillCatalogDefaultLimit,
  }) async {
    AssistantSkillCatalogItemView item({
      required String skillId,
      required String displayName,
      required String description,
      String? category,
      String? iconHint,
      String domainId = 'assistant',
      List<String> requiredConsentScopes = const <String>[],
      SkillActivationMode activationMode = SkillActivationMode.hybrid,
    }) {
      return AssistantSkillCatalogItemView(
        packageId: 'quwoquan.official.$skillId',
        releaseDigest: canonicalFixtureSha256(<String, Object?>{
          'packageId': 'quwoquan.official.$skillId',
          'skillId': skillId,
        }),
        skillId: skillId,
        domainId: domainId,
        displayName: displayName,
        description: description,
        catalogGroup: _fixtureSemanticLabel(category ?? 'general'),
        requiresConsent: requiredConsentScopes.isNotEmpty,
        requiredConsentScopes: requiredConsentScopes,
        consentScopeLabels: requiredConsentScopes
            .map(_fixtureSemanticLabel)
            .toList(growable: false),
        iconHint: iconHint,
        targetAudiences: <SkillCatalogSemanticLabel>[
          _fixtureSemanticLabel('trip_organizer'),
        ],
        dataUseSummary: requiredConsentScopes.isEmpty
            ? '仅使用当前对话与公开信息'
            : '仅在明确授权后读取所列数据',
        examples: const <ResolvedSkillExample>[],
        activationMode: activationMode,
        surfaceKinds: <SkillCatalogSemanticLabel>[
          _fixtureSemanticLabel('personal'),
        ],
        configurationSchemaDigest: canonicalFixtureSha256(<String, Object?>{
          'skillId': skillId,
          'configurationRequiredFields': const <String>[],
        }),
        setupTemplateRef: 'assistant.setup.$skillId',
        configurationRequiredFields: const <String>[],
      );
    }

    final primarySkills = <AssistantSkillCatalogItemView>[
      item(
        skillId: 'daily_assistant',
        displayName: '每日助手',
        description: '管理待办、日历、会议、作息和学习计划。',
        category: 'life',
        iconHint: 'checkmark',
      ),
      item(
        skillId: 'news_briefing',
        displayName: '新闻简报',
        description: '按关注话题定时生成新闻摘要。',
        category: 'content',
        iconHint: 'news',
      ),
      item(
        skillId: 'stock_sentinel',
        displayName: '股票哨兵',
        description: '跟踪关注股票的重大消息面和行情变化。',
        category: 'finance',
        iconHint: 'chart',
      ),
      item(
        skillId: 'travel_companion',
        displayName: '出行旅程管家',
        description: '结合天气、路况和景点拥堵提醒行程风险。',
        category: 'travel',
        iconHint: 'airplane',
        domainId: 'travel',
        requiredConsentScopes: const <String>[
          'assistant.learning.feedback_context.read',
          'assistant.memory.preferences.read',
        ],
      ),
      item(
        skillId: 'creation_assistant',
        displayName: '创作助手',
        description: '帮助整理草稿摘要、推荐标签和关联主页。',
        category: 'content_creation',
        iconHint: 'sparkles',
      ),
    ];
    final prototypeSkills = _prototypeSkills.map(
      (row) => item(
        skillId: row.skillId,
        displayName: row.name,
        description: row.description ?? '',
      ),
    );
    return <AssistantSkillCatalogItemView>[
      ...primarySkills,
      ...prototypeSkills,
    ].take(limit).toList(growable: false);
  }

  @override
  Future<AssistantSkillCatalogItemDetailView> getSkillCatalogItem({
    required String skillId,
  }) async {
    final item = (await listSkillCatalog()).singleWhere(
      (candidate) => candidate.skillId == skillId,
      orElse: () => throw StateError('skill catalog item not found'),
    );
    final configurationSchema = skillId == 'travel_companion'
        ? <String, Object?>{
            'title': '旅行偏好',
            'description': '用于组合吃玩住行与提醒节奏。',
            'type': 'object',
            'additionalProperties': false,
            'properties': <String, Object?>{
              'travelPace': <String, Object?>{
                'type': 'string',
                'title': '旅行节奏',
                'enum': <String>['relaxed', 'balanced', 'intensive'],
                'x-enum-labels': <String, String>{
                  'relaxed': '轻松',
                  'balanced': '均衡',
                  'intensive': '紧凑',
                },
              },
              'reminderLeadMinutes': <String, Object?>{
                'type': 'integer',
                'title': '默认提前提醒',
                'minimum': 5,
                'maximum': 1440,
              },
            },
          }
        : <String, Object?>{
            'type': 'object',
            'additionalProperties': false,
            'properties': <String, Object?>{},
          };
    return AssistantSkillCatalogItemDetailView(
      item: item,
      configurationSchema: configurationSchema,
    );
  }
}

const Map<String, String> _fixtureSemanticLabelTexts = <String, String>{
  'general': '通用',
  'life': '生活',
  'content': '内容',
  'finance': '财经',
  'travel': '旅行',
  'content_creation': '创作',
  'personal': '个人助理',
  'conversation': '会话',
  'circle': '圈子',
  'trip_organizer': '旅行组织者',
  'assistant.memory.preferences.read': '读取助手偏好',
  'assistant.learning.feedback_context.read': '使用脱敏的助手反馈摘要',
};

SkillCatalogSemanticLabel _fixtureSemanticLabel(String id) =>
    SkillCatalogSemanticLabel(
      id: id,
      displayText: _fixtureSemanticLabelTexts[id] ?? '标签·$id',
    );
