// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-shared-timeline/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/content/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/content/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/travel/travel/trip_share_snapshot/presentation/trip_share_page.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets(
    'share snapshot creates and opens one editable local travelogue',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final repository = _MemoryDraftRepository();
      String? openedDraftId;

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            tripShareSnapshotProvider(
              'share-1',
            ).overrideWith((ref) async => _snapshot()),
            createDraftRepositoryProvider.overrideWithValue(repository),
          ],
          child: MaterialApp(
            home: TripSharePage(
              snapshotId: 'share-1',
              onBack: () {},
              onOpenDraft: (draftId) => openedDraftId = draftId,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(TravelText.sharePrivacySafe), findsOneWidget);
      expect(find.text(TravelText.createTravelogue), findsOneWidget);
      await tester.tap(find.text(TravelText.createTravelogue));
      await tester.pump();
      await tester.pump();

      expect(openedDraftId, 'travelogue-share-1');
      final draft = repository.state.draftById(openedDraftId!);
      expect(draft?.state.title, TravelText.travelogueDraftTitle);
      expect(draft?.state.body, contains('西湖晨游'));
      expect(draft?.state.settings.isPublic, isTrue);
      await tester.pump(const Duration(seconds: 4));
      expect(tester.takeException(), isNull);
    },
  );
}

TripShareSnapshot _snapshot() {
  return TripShareSnapshot(
    id: 'share-1',
    version: 1,
    tripId: 'trip-1',
    sourceRevisionId: 'revision-1',
    sourceRevisionNumber: 1,
    sourceDigest:
        'sha256:41cf6794ba4200b839c53531555f0f3998df4cbb01a4d5cb0b94e3ca5e23947d',
    scope: TripShareSnapshotScope.full,
    momentIds: const <String>[],
    visibility: TripShareSnapshotVisibility.public,
    privacyPolicyDigest:
        'sha256:760672367557300130bdf88db43b01f07917475ae4f60ff0b9be95aa78d7e2f1',
    items: const <TripShareItemSlice>[
      TripShareItemSlice(
        dayIndex: 1,
        itemId: 'item-1',
        orderInDay: 1,
        kind: 'sight',
        title: '西湖晨游',
      ),
    ],
    moments: const <TripShareMomentSlice>[],
    contentLinks: const <TripShareContentLinkSlice>[],
    routeStops: const <TripShareRouteStopSlice>[],
    createdByPersonaId: 'persona-1',
    status: TripShareSnapshotStatus.active,
    createdAt: DateTime.utc(2026, 8, 2, 10),
  );
}

final class _MemoryDraftRepository implements CreateDraftRepository {
  CreateDraftStoreState state = const CreateDraftStoreState();

  @override
  Future<CreateDraftStoreState> deleteDraft(String draftId) async => state;

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
      drafts: <CreateDraft>[draft],
      currentDraftId: currentDraftId,
    );
    return state;
  }
}
