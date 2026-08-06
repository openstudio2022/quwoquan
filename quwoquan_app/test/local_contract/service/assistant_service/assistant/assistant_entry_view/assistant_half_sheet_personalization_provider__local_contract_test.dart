// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-001
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/adapters/assistant_open_context_mapper.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/presentation/assistant_half_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_facets_typed_double.dart';

class _TrackingAssistantRepository extends InMemoryAssistantFacets {
  final List<String> calls = <String>[];
  AssistantContextSnapshot? lastContextSnapshot;

  @override
  Future<PageContextReceipt> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    calls.add('reportPageContext:$userAction');
    lastContextSnapshot = assistantContextSnapshotFromOpenContext(
      context,
      userAction: userAction,
    );
    return PageContextReceipt(
      accepted: true,
      contextKey: 'ctx_test',
      expiresAt: '2026-08-02T12:05:00Z',
    );
  }

  @override
  Future<AssistantEntryResponse> getAssistantEntry({
    required AssistantOpenContext context,
  }) async {
    calls.add('getAssistantEntry');
    return const AssistantEntryResponse(
      welcomeMessage: '服务端欢迎语',
      suggestionLines: <String>['服务端建议'],
      chips: <AssistantEntryChip>[
        AssistantEntryChip(
          chipId: 'server_find',
          label: '服务端找资料',
          actionType: 'command',
          value: 'find',
        ),
      ],
      actions: <AssistantEntryAction>[
        AssistantEntryAction(
          actionId: 'server_action',
          actionType: 'command',
          label: '服务端动作',
        ),
      ],
      personalized: true,
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
        experienceLevel: AssistantExperienceLevel.returning,
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
        'getAssistantEntry',
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
        isNull,
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
