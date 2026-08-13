// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/spec.md#req-002
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show
        assistantSkillCatalogFacetProvider,
        assistantSkillSurfacePlacementFacetProvider;
import 'package:quwoquan_app/service/assistant_service/assistant/skill_surface_placement/presentation/assistant_skill_placement_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/skill_catalog/skill_catalog_typed_double.dart';
import '../../../../../support/service/assistant_service/assistant/skill_surface_placement/skill_surface_placement_typed_double.dart';

SkillSurfacePlacement _placement({
  List<String> disabledSkillIds = const <String>[],
  int revision = 3,
}) {
  return SkillSurfacePlacement(
    id: 'placement:conversation:conv-42',
    surfaceKind: SkillSurfaceKind.conversation,
    surfaceId: 'conv-42',
    policy: SkillSurfacePlacementPolicy.allSharedEligible,
    disabledSkillIds: disabledSkillIds,
    status: SkillSurfacePlacementStatus.active,
    revision: revision,
    createdAt: '2026-08-01T00:00:00Z',
    updatedAt: '2026-08-02T00:00:00Z',
  );
}

Widget _buildApp(InMemoryAssistantSkillSurfacePlacementFacet placementFacet) {
  return ProviderScope(
    overrides: [
      assistantSkillSurfacePlacementFacetProvider.overrideWithValue(
        placementFacet,
      ),
      assistantSkillCatalogFacetProvider.overrideWithValue(
        InMemoryAssistantSkillCatalogFacet(),
      ),
    ],
    child: MaterialApp(
      locale: const Locale('zh'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
        builder: (context) => CupertinoButton(
          key: const ValueKey<String>('open_placement_sheet'),
          onPressed: () => showAssistantSkillPlacementSheet(
            context: context,
            surfaceKind: SkillSurfaceKind.conversation,
            surfaceId: 'conv-42',
          ),
          child: const Text('open'),
        ),
      ),
    ),
  );
}

Future<void> _openSheet(WidgetTester tester) async {
  await tester.tap(
    find.byKey(const ValueKey<String>('open_placement_sheet')),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('placement 面板展示服务端共享策略与禁用清单', (tester) async {
    final placementFacet = InMemoryAssistantSkillSurfacePlacementFacet(
      placements: <SkillSurfacePlacement>[
        _placement(disabledSkillIds: const <String>['news_briefing']),
      ],
    );
    await tester.pumpWidget(_buildApp(placementFacet));
    await _openSheet(tester);

    expect(
      find.byKey(const ValueKey<String>('assistant_skill_placement_sheet')),
      findsOneWidget,
    );
    expect(
      find.text(AssistantText.assistantSkillPlacementPolicyAllShared),
      findsOneWidget,
    );
    final disabledToggle = tester.widget<CupertinoSwitch>(
      find.byKey(
        const ValueKey<String>(
          'assistant_skill_placement_toggle_news_briefing',
        ),
      ),
    );
    expect(disabledToggle.value, isFalse);
    final enabledToggle = tester.widget<CupertinoSwitch>(
      find.byKey(
        const ValueKey<String>(
          'assistant_skill_placement_toggle_daily_assistant',
        ),
      ),
    );
    expect(enabledToggle.value, isTrue);
  });

  testWidgets('管理员禁用共享 Skill 走 revision CAS 保存', (tester) async {
    final placementFacet = InMemoryAssistantSkillSurfacePlacementFacet(
      placements: <SkillSurfacePlacement>[
        _placement(disabledSkillIds: const <String>['news_briefing']),
      ],
    );
    await tester.pumpWidget(_buildApp(placementFacet));
    await _openSheet(tester);

    await tester.tap(
      find.byKey(
        const ValueKey<String>(
          'assistant_skill_placement_toggle_travel_companion',
        ),
      ),
    );
    await tester.pump();
    final saveButton = find.byKey(
      const ValueKey<String>('assistant_skill_placement_save'),
    );
    await tester.ensureVisible(saveButton);
    await tester.tap(saveButton);
    await tester.pumpAndSettle();

    final receipt = placementFacet.putReceipts.single;
    expect(receipt.clientRequestId, isNotEmpty);
    expect(receipt.saved.disabledSkillIds, <String>[
      'news_briefing',
      'travel_companion',
    ]);
    expect(receipt.saved.policy, SkillSurfacePlacementPolicy.allSharedEligible);
    expect(receipt.saved.status, SkillSurfacePlacementStatus.active);
    expect(receipt.saved.revision, 4);
    // 保存成功后面板关闭。
    expect(
      find.byKey(const ValueKey<String>('assistant_skill_placement_sheet')),
      findsNothing,
    );
  });

  testWidgets('revision 冲突时保存失败并保留面板与错误提示', (tester) async {
    final placementFacet = InMemoryAssistantSkillSurfacePlacementFacet(
      placements: <SkillSurfacePlacement>[
        // 面板读取 revision 3 之后，服务端已推进到 5：CAS 必然冲突。
        _placement(revision: 3),
      ],
    );
    await tester.pumpWidget(_buildApp(placementFacet));
    await _openSheet(tester);

    await placementFacet.putSkillSurfacePlacement(
      surfaceKind: SkillSurfaceKind.conversation,
      surfaceId: 'conv-42',
      policy: SkillSurfacePlacementPolicy.allSharedEligible,
      disabledSkillIds: const <String>[],
      status: SkillSurfacePlacementStatus.active,
      expectedRevision: 3,
      clientRequestId: 'concurrent-admin',
    );

    await tester.tap(
      find.byKey(
        const ValueKey<String>(
          'assistant_skill_placement_toggle_daily_assistant',
        ),
      ),
    );
    await tester.pump();
    final saveButton = find.byKey(
      const ValueKey<String>('assistant_skill_placement_save'),
    );
    await tester.ensureVisible(saveButton);
    await tester.tap(saveButton);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('assistant_skill_placement_sheet')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('assistant_skill_placement_error')),
      findsOneWidget,
    );
    // 冲突写入没有生效：服务端仍是并发管理员保存的状态。
    expect(
      placementFacet.putReceipts.single.clientRequestId,
      'concurrent-admin',
    );
  });
}
