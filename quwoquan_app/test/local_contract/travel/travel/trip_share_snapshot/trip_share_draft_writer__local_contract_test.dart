// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/application/trip_travelogue_draft.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/adapters/trip_share_draft_writer.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'public travel snapshot is upserted as one editable article draft',
    () async {
      final repository = _MemoryDraftRepository();
      final writer = TripShareDraftWriter(
        repository: repository,
        clock: () => 1234,
      );

      final savedId = await writer.save(_source(), _content());

      expect(savedId, 'travelogue-share-1');
      final draft = repository.state.draftById(savedId);
      expect(draft, isNotNull);
      expect(draft?.updatedAtMs, 1234);
      expect(draft?.sourceType, 'article');
      expect(draft?.state.title, '我的旅行游记');
      expect(draft?.state.body, contains('第1天'));
      expect(draft?.state.body, contains('西湖晨游'));
      expect(draft?.state.draftFlowKind, CreateDraftFlowKind.article);
      expect(draft?.state.settings.isPublic, isTrue);
      expect(draft?.state.settings.entityRefs, <String>[
        'travel.TripShareSnapshot:share-1@1',
      ]);
      expect(
        draft?.publicationContinuation?.operationId,
        AppCloudOperationIds.travelTripPlanContentLinkPutTripPlanContentLink,
      );
      expect(
        draft?.publicationContinuation?.sourceEntityRef,
        'travel.TripShareSnapshot:share-1@1',
      );
      final restored = CreateDraft.fromStorageMap(draft!.toStorageMap());
      expect(
        restored.publicationContinuation?.operationId,
        draft.publicationContinuation?.operationId,
      );
      expect(
        restored.publicationContinuation?.sourceEntityRef,
        draft.publicationContinuation?.sourceEntityRef,
      );
      expect(repository.state.currentDraftId, savedId);
    },
  );

  test('member-only snapshot never adds a public entity reference', () async {
    final repository = _MemoryDraftRepository();
    final writer = TripShareDraftWriter(
      repository: repository,
      clock: () => 1234,
    );

    await writer.save(
      _source(visibility: TripShareSnapshotVisibility.tripMembers),
      _content(),
    );

    final draft = repository.state.draftById('travelogue-share-1');
    expect(draft?.state.settings.isPublic, isFalse);
    expect(draft?.state.settings.entityRefs, isEmpty);
  });
}

TripTravelogueDraftSource _source({
  TripShareSnapshotVisibility visibility = TripShareSnapshotVisibility.public,
}) {
  return TripTravelogueDraftSource(
    localDraftId: 'travelogue-share-1',
    snapshotId: 'share-1',
    snapshotVersion: 1,
    tripId: 'trip-1',
    sourceRevisionId: 'revision-1',
    sourceRevisionNumber: 1,
    sourceDigest:
        'sha256:41cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947d',
    privacyPolicyDigest:
        'sha256:760672367557300130bdf88db43b01f07917475ae4f60ff0b9be95aa78d7e2f1',
    scope: TripShareSnapshotScope.full,
    visibility: visibility,
    days: const <TripTravelogueDaySource>[],
  );
}

TripTravelogueDraftContent _content() {
  return TripTravelogueDraftContent(
    title: '我的旅行游记',
    summary: '可编辑旅行时间线',
    blocks: const <TripTravelogueDraftBlock>[
      TripTravelogueDraftBlock(
        kind: TripTravelogueDraftBlockKind.heading,
        text: '第1天',
      ),
      TripTravelogueDraftBlock(
        kind: TripTravelogueDraftBlockKind.orderedItem,
        text: '西湖晨游',
      ),
    ],
  );
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
    state = state.copyWith(currentDraftId: draftId);
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
