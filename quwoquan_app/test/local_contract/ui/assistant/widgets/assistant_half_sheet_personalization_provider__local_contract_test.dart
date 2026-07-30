// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-001
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';

import '../../../../support/cloud_services/assistant_facets_mock.dart';

class _TrackingAssistantRepository extends AlphaAssistantFacets {
  final List<String> calls = <String>[];
  AssistantContextSnapshot? lastContextSnapshot;

  @override
  Future<PageContextAck> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    calls.add('reportPageContext:$userAction');
    lastContextSnapshot = assistantContextSnapshotFromOpenContext(
      context,
      userAction: userAction,
    );
    return const PageContextAck(accepted: true, contextKey: 'ctx_test');
  }

  @override
  Future<AssistantEntryPersonalizationView> getEntryPersonalization({
    required AssistantOpenContext context,
  }) async {
    calls.add('getEntryPersonalization');
    return const AssistantEntryPersonalizationView(
      welcomeMessage: '服务端欢迎语',
      suggestionLines: <String>['服务端建议'],
      chips: <AssistantEntryPersonalizationChipView>[
        AssistantEntryPersonalizationChipView(
          chipId: 'server_find',
          label: '服务端找资料',
          actionType: 'command',
          value: 'find',
        ),
      ],
      personalized: true,
    );
  }

  @override
  Future<SuggestedActionListView> getSuggestedActions({
    required AssistantOpenContext context,
  }) async {
    calls.add('getSuggestedActions');
    return const SuggestedActionListView(
      items: <SuggestedAction>[
        SuggestedAction(
          actionId: 'server_action',
          type: 'command',
          label: '服务端动作',
        ),
      ],
    );
  }
}

void main() {
  test(
    'half sheet personalization reports page context before loading entry data',
    () async {
      final repo = _TrackingAssistantRepository();
      final context = AssistantOpenContext(
        source: AssistantSource.article,
        visitTarget: const VisitTarget.page('article'),
        experienceLevel: ExperienceLevel.returning,
        entityId: 'post_001',
        objectType: 'content.post',
        intersectionEvidenceRefs: const <AssistantIntersectionEvidenceRef>[
          AssistantIntersectionEvidenceRef(
            intersectionId: 'intersection-001',
            evidenceId: 'snapshot-001',
            sourceRef: 'travel_companion',
            objectTypeRef: 'content.post',
            objectId: 'post_001',
          ),
        ],
      );
      final container = ProviderContainer(
        overrides: [
          assistantPersonalizationFacetProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);

      final value = await container.read(
        assistantHalfSheetPersonalizationProvider(context).future,
      );

      expect(repo.calls, <String>[
        'reportPageContext:open_assistant_entry',
        'getEntryPersonalization',
        'getSuggestedActions',
      ]);
      expect(value.welcomeMessage, '服务端欢迎语');
      expect(value.chips.single.label, '服务端找资料');
      expect(value.suggestionLines, <String>['服务端建议']);
      expect(value.suggestedActions.single.actionId, 'server_action');
      expect(
        repo.lastContextSnapshot?.pageType,
        AssistantPageContextType.article,
      );
      expect(repo.lastContextSnapshot?.pageObjects, hasLength(1));
      expect(
        repo.lastContextSnapshot?.userActions?.single.action,
        'open_assistant_entry',
      );
      expect(
        repo.lastContextSnapshot?.intersectionEvidenceRefs,
        isEmpty,
        reason: '页面上下文上报不得代替 StartAssistantRun 提交交集证据引用',
      );
    },
  );

  test(
    'assistant page context maps every product source to canonical type',
    () {
      expect(
        assistantPageTypeForSource(AssistantSource.home),
        AssistantPageContextType.home,
      );
      expect(
        assistantPageTypeForSource(AssistantSource.discovery),
        AssistantPageContextType.discovery,
      );
      expect(
        assistantPageTypeForSource(AssistantSource.circles),
        AssistantPageContextType.circles,
      );
      expect(
        assistantPageTypeForSource(AssistantSource.article),
        AssistantPageContextType.article,
      );
      expect(
        assistantPageTypeForSource(AssistantSource.profile),
        AssistantPageContextType.profile,
      );
      expect(
        assistantPageTypeForSource(AssistantSource.chat),
        AssistantPageContextType.chat,
      );
      expect(
        assistantPageTypeForSource(AssistantSource.create),
        AssistantPageContextType.create,
      );
      expect(
        assistantPageTypeForSource(AssistantSource.search),
        AssistantPageContextType.search,
      );
    },
  );
}
