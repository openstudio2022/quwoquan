// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/gathering_travelogue_draft_dependencies.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_share_capability.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_travelogue_draft.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_journey_travelogue_draft_composer.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';

void main() {
  test(
    'Circle privacy snapshot produces deterministic editable semantics',
    () async {
      final writer = _RecordingWriter();
      final coordinator = GatheringJourneyTravelogueDraftCoordinator(
        composer: const GatheringTravelTextTravelogueDraftComposer(),
        writer: writer,
        draftIdFactory: (snapshotId) => 'travelogue-$snapshotId',
      );

      final firstId = await coordinator.create(_snapshot());
      final retryId = await coordinator.create(_snapshot());

      expect(firstId, 'travelogue-share-1');
      expect(retryId, firstId);
      expect(writer.sources, hasLength(2));
      final source = writer.sources.first;
      expect(
        source.sourceEntityRef,
        'circle.GatheringJourneyShareSnapshot:share-1@2',
      );
      expect(source.gatheringId, 'gathering-1');
      expect(source.days.map((day) => day.dayIndex), <int>[1]);
      expect(
        source.days.single.entries.map((entry) => entry.sourceRef.objectId),
        <String>['plan-item-1', 'plan-item-2'],
      );
      expect(
        writer.contents.first.blocks.map((block) => block.text),
        containsAllInOrder(<String>[
          '沿着共同计划与旅途记录，继续补充当时的故事。',
          '第1天',
          '西湖晨游',
          '湖边午餐',
        ]),
      );
    },
  );

  test(
    'Content adapter persists Circle source and injected continuation',
    () async {
      final repository = _MemoryDraftRepository();
      const operationId = 'circle.gathering.content_reference.put';
      final writer = GatheringShareDraftWriter(
        repository: repository,
        clock: () => 1234,
        publicationContinuationOperationId: operationId,
      );
      final source = GatheringJourneyTravelogueDraftCoordinator(
        composer: const GatheringTravelTextTravelogueDraftComposer(),
        writer: _RecordingWriter(),
        draftIdFactory: (snapshotId) => 'travelogue-$snapshotId',
      ).buildSource(_snapshot());
      final content = const GatheringTravelTextTravelogueDraftComposer()
          .compose(source);

      final savedId = await writer.save(source, content);

      final draft = repository.state.draftById(savedId);
      expect(draft?.updatedAtMs, 1234);
      expect(draft?.state.settings.isPublic, isTrue);
      expect(draft?.state.settings.entityRefs, <String>[
        'circle.GatheringJourneyShareSnapshot:share-1@2',
      ]);
      expect(draft?.publicationContinuation?.operationId, operationId);
      expect(repository.state.currentDraftId, savedId);
    },
  );

  test('empty snapshot and blank continuation fail closed', () async {
    final coordinator = GatheringJourneyTravelogueDraftCoordinator(
      composer: const GatheringTravelTextTravelogueDraftComposer(),
      writer: _RecordingWriter(),
      draftIdFactory: (_) => 'draft',
    );
    expect(
      () => coordinator.buildSource(_snapshot(entries: const [])),
      throwsArgumentError,
    );

    final writer = GatheringShareDraftWriter(
      repository: _MemoryDraftRepository(),
      clock: () => 1,
      publicationContinuationOperationId: ' ',
    );
    final source = coordinator.buildSource(_snapshot());
    final content = const GatheringTravelTextTravelogueDraftComposer().compose(
      source,
    );
    await expectLater(writer.save(source, content), throwsStateError);
  });
}

GatheringJourneyShareSnapshot _snapshot({
  List<GatheringJourneyShareEntry>? entries,
}) {
  return GatheringJourneyShareSnapshot(
    snapshotId: 'share-1',
    version: 2,
    gatheringId: 'gathering-1',
    sourceDigest:
        'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    privacyPolicyDigest:
        'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    selection: const GatheringJourneyShareSelection.full(),
    entries:
        entries ??
        const <GatheringJourneyShareEntry>[
          GatheringJourneyShareEntry(
            sourceRef: GatheringCanonicalObjectRef(
              objectTypeRef: 'circle.GatheringPlanItem',
              objectId: 'plan-item-2',
            ),
            sourceVersion: 3,
            sourceDigest:
                'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
            title: '湖边午餐',
            dayIndex: 1,
            planItemId: 'plan-item-2',
          ),
          GatheringJourneyShareEntry(
            sourceRef: GatheringCanonicalObjectRef(
              objectTypeRef: 'circle.GatheringPlanItem',
              objectId: 'plan-item-1',
            ),
            sourceVersion: 3,
            sourceDigest:
                'sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
            title: '西湖晨游',
            dayIndex: 1,
            planItemId: 'plan-item-1',
          ),
        ],
  );
}

final class _RecordingWriter implements GatheringJourneyTravelogueDraftWriter {
  final List<GatheringJourneyTravelogueDraftSource> sources =
      <GatheringJourneyTravelogueDraftSource>[];
  final List<GatheringJourneyTravelogueDraftContent> contents =
      <GatheringJourneyTravelogueDraftContent>[];

  @override
  Future<String> save(
    GatheringJourneyTravelogueDraftSource source,
    GatheringJourneyTravelogueDraftContent content,
  ) async {
    sources.add(source);
    contents.add(content);
    return source.localDraftId;
  }
}

final class _MemoryDraftRepository implements CreateDraftRepository {
  CreateDraftStoreState state = const CreateDraftStoreState();

  @override
  Future<CreateDraftStoreState> deleteDraft(String draftId) async {
    state = CreateDraftStoreState(
      drafts: state.drafts.where((draft) => draft.id != draftId).toList(),
    );
    return state;
  }

  @override
  Future<CreateDraftStoreState> load() async => state;

  @override
  Future<CreateDraft?> loadDraft(String draftId) async =>
      state.draftById(draftId);

  @override
  Future<CreateDraftStoreState> setCurrentDraftId(String? draftId) async {
    state = CreateDraftStoreState(
      drafts: state.drafts,
      currentDraftId: draftId,
    );
    return state;
  }

  @override
  Future<CreateDraftStoreState> upsertDraft(
    CreateDraft draft, {
    String? currentDraftId,
  }) async {
    state = CreateDraftStoreState(
      drafts: <CreateDraft>[
        draft,
        ...state.drafts.where((candidate) => candidate.id != draft.id),
      ],
      currentDraftId: currentDraftId,
    );
    return state;
  }
}
