// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_setup_schema.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_setup_sheet.dart';

void main() {
  testWidgets('renders package schema and saves only validated values', (
    tester,
  ) async {
    Map<String, Object?>? saved;
    final schema = AssistantSkillSetupSchema.tryParse(<String, Object?>{
      'title': '旅行偏好',
      'type': 'object',
      'additionalProperties': false,
      'required': <String>['pace'],
      'properties': <String, Object?>{
        'pace': <String, Object?>{
          'type': 'string',
          'title': '旅行节奏',
          'enum': <String>['relaxed', 'balanced'],
          'x-enum-labels': <String, String>{'relaxed': '轻松', 'balanced': '均衡'},
        },
        'lead': <String, Object?>{
          'type': 'integer',
          'title': '提前提醒',
          'minimum': 5,
          'maximum': 60,
        },
      },
    });
    await tester.pumpWidget(
      CupertinoApp(
        home: AssistantSkillSetupSheet(
          title: '贴身旅行管家',
          valueDescription: '一路计划，一路记录。',
          dataUseSummary: '只读取已授权的行程。',
          targetUserLabels: const <String>['旅行组织者'],
          surfaceLabels: const <String>['个人', '群聊'],
          requiredPermissionScopes:
              const <AssistantSkillConsentScopePresentation>[
                AssistantSkillConsentScopePresentation(
                  displayText: '读取行程',
                  description: '用于行程规划',
                  granted: true,
                ),
              ],
          optionalPermissionScopes:
              const <AssistantSkillConsentScopePresentation>[
                AssistantSkillConsentScopePresentation(
                  displayText: '使用脱敏反馈摘要',
                  description: '不读取原始文字',
                  granted: false,
                ),
              ],
          schema: schema,
          initialConfiguration: const <String, Object?>{
            'pace': 'balanced',
            'unknown': 'must-not-survive',
          },
          onSave: (value) async => saved = value,
        ),
      ),
    );

    expect(find.text('旅行偏好'), findsOneWidget);
    expect(find.text('均衡'), findsOneWidget);
    expect(find.text('unknown'), findsNothing);
    expect(
      find.text(AssistantText.assistantSkillRequiredConsentScopes),
      findsOneWidget,
    );
    expect(
      find.text(AssistantText.assistantSkillOptionalConsentScopes),
      findsOneWidget,
    );
    expect(find.textContaining('读取行程'), findsOneWidget);
    expect(find.textContaining('使用脱敏反馈摘要'), findsOneWidget);
    await tester.enterText(
      find.byKey(const ValueKey<String>('assistant_skill_setup_input_lead')),
      '30',
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('assistant_skill_setup_save')),
    );
    await tester.pumpAndSettle();

    expect(saved, <String, Object?>{'pace': 'balanced', 'lead': 30});
  });

  testWidgets('shows fail-closed state when schema is unsupported', (
    tester,
  ) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: AssistantSkillSetupSheet(
          title: 'Skill',
          valueDescription: '',
          dataUseSummary: '',
          targetUserLabels: <String>[],
          surfaceLabels: <String>[],
          requiredPermissionScopes: <AssistantSkillConsentScopePresentation>[],
          optionalPermissionScopes: <AssistantSkillConsentScopePresentation>[],
          schema: null,
          initialConfiguration: <String, Object?>{},
          onSave: null,
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey<String>('assistant_skill_setup_unavailable')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('assistant_skill_setup_save')),
      findsNothing,
    );
  });

  testWidgets('does not silently drop an invalid optional integer', (
    tester,
  ) async {
    final schema = AssistantSkillSetupSchema.tryParse(<String, Object?>{
      'type': 'object',
      'additionalProperties': false,
      'properties': <String, Object?>{
        'lead': <String, Object?>{
          'type': 'integer',
          'title': '提前提醒',
          'minimum': 5,
        },
      },
    });
    await tester.pumpWidget(
      CupertinoApp(
        home: AssistantSkillSetupSheet(
          title: 'Skill',
          valueDescription: '',
          dataUseSummary: '',
          targetUserLabels: const <String>[],
          surfaceLabels: const <String>[],
          requiredPermissionScopes:
              const <AssistantSkillConsentScopePresentation>[],
          optionalPermissionScopes:
              const <AssistantSkillConsentScopePresentation>[],
          schema: schema,
          initialConfiguration: const <String, Object?>{},
          onSave: (_) async {},
        ),
      ),
    );
    await tester.enterText(
      find.byKey(const ValueKey<String>('assistant_skill_setup_input_lead')),
      'later',
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('assistant_skill_setup_save')),
    );
    await tester.pump();

    expect(find.text('提前提醒必须是整数'), findsOneWidget);
  });
}
