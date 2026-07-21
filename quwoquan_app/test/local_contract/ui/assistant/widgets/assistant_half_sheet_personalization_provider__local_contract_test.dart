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
  Map<String, dynamic>? lastContextSnapshot;

  @override
  Future<PageContextAck> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
    List<Map<String, dynamic>> userActions = const <Map<String, dynamic>>[],
  }) async {
    calls.add('reportPageContext:$userAction');
    lastContextSnapshot = assistantContextSnapshotFromOpenContext(context);
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
      expect(value.suggestionLines, <String>['服务端动作']);
      expect(repo.lastContextSnapshot?['pageType'], 'home');
      expect(repo.lastContextSnapshot?['pageObjects'], isA<List<dynamic>>());
      expect(
        repo.lastContextSnapshot?['intersectionEvidenceRefs'],
        isA<List<dynamic>>(),
      );
    },
  );
}
