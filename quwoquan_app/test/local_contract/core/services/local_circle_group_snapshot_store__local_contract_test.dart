import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_record.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/sqflite_ffi_test_support.dart';

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  group('LocalCircleGroupSnapshotStore', () {
    late Directory tempDir;
    late LocalCircleGroupSnapshotStore store;
    late LocalSearchNamespace ownerNamespace;
    late LocalSearchNamespace subNamespace;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp(
        'local_circle_snapshot_test_',
      );
      store = LocalCircleGroupSnapshotStore(
        databasePath: '${tempDir.path}/circle_groups.db',
      );
      ownerNamespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          subAccountId: 'user_owner',
          ownerUserId: 'user_owner',
          subjectType: 'owner',
          displayName: '主账号',
          avatarUrl: '',
          personaContextVersion: 'v1',
        ),
      );
      subNamespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          subAccountId: 'sub_001',
          ownerUserId: 'user_owner',
          subjectType: 'sub_account',
          displayName: '子账号',
          avatarUrl: '',
          personaContextVersion: 'v2',
        ),
      );
      await store.ensureReady();
    });

    tearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test(
      'isolates snapshots by namespace and deletes only target namespace',
      () async {
        await store.upsertGroups(
          namespace: ownerNamespace,
          groups: const <LocalCircleGroupSnapshotRecord>[
            LocalCircleGroupSnapshotRecord(
              circleId: 'fixture_circle_photo',
              groupId: 'group_photo',
              name: '光影摄影社主群',
              description: '摄影讨论',
              circleName: '光影摄影社',
              groupType: 'public_group',
              visibility: 'public',
              updatedAt: '2026-07-14T00:00:00.000Z',
            ),
          ],
        );
        await store.upsertGroups(
          namespace: subNamespace,
          groups: const <LocalCircleGroupSnapshotRecord>[
            LocalCircleGroupSnapshotRecord(
              circleId: 'circle_trip_01',
              groupId: 'group_trip',
              name: '旅行手账主群',
              description: '旅行讨论',
              circleName: '旅行手账',
              groupType: 'public_group',
              visibility: 'public',
              updatedAt: '2026-07-14T00:00:00.000Z',
            ),
          ],
        );

        expect(
          await store.searchGroups(namespace: ownerNamespace, query: '摄影'),
          hasLength(1),
        );
        expect(
          await store.searchGroups(namespace: subNamespace, query: '摄影'),
          isEmpty,
        );

        await store.deleteNamespace(ownerNamespace);

        expect(await store.hasAnySnapshot(ownerNamespace), isFalse);
        expect(await store.hasAnySnapshot(subNamespace), isTrue);
        expect(
          await store.searchGroups(namespace: subNamespace, query: '旅行'),
          hasLength(1),
        );
      },
    );

    test(
      'ensureSeeded is deduped per namespace and reseeds new namespace',
      () async {
        final reader = _CountingCircleQueryReader();
        const groups = _CountingCircleGroupQuery();

        expect(
          await store.ensureSeeded(
            namespace: ownerNamespace,
            circleQuery: reader,
            circleGroupQuery: groups,
          ),
          isTrue,
        );
        expect(
          await store.ensureSeeded(
            namespace: ownerNamespace,
            circleQuery: reader,
            circleGroupQuery: groups,
          ),
          isTrue,
        );
        final ownerListCalls = reader.listCalls;

        expect(
          await store.ensureSeeded(
            namespace: subNamespace,
            circleQuery: reader,
            circleGroupQuery: groups,
          ),
          isTrue,
        );

        expect(ownerListCalls, equals(1));
        expect(reader.listCalls, equals(2));
        expect(await store.hasAnySnapshot(ownerNamespace), isTrue);
        expect(await store.hasAnySnapshot(subNamespace), isTrue);
      },
    );
  });
}

final class _CountingCircleQueryReader implements CircleQueryReader {
  int listCalls = 0;

  @override
  Future<CirclePageSlice> list(CircleListQuery query) async {
    listCalls += 1;
    return CirclePageSlice(
      items: <CircleProjection>[
        CircleProjection(
          circleId: 'fixture_circle_photo',
          name: '契约摄影社',
          ownerId: 'fixture_owner',
        ),
      ],
    );
  }

  @override
  Future<CircleSearchResultSlice> search(CircleSearchQuery query) async =>
      CircleSearchResultSlice(
        items: const <CircleSearchItemProjection>[],
        facetBuckets: const <CircleFacetBucketProjection>[],
      );

  @override
  Future<CircleProjection> get(CircleDetailQuery query) async =>
      throw UnimplementedError();

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query) async =>
      CircleFeedPageSlice(items: const <CircleFeedPostProjection>[]);

  @override
  Future<CircleStatsSlice> stats(CircleStatsQuery query) async =>
      const CircleStatsSlice();

  @override
  Future<CircleImpactSlice> impact(CircleImpactQuery query) async =>
      CircleImpactSlice(
        circleId: query.circleId,
        total: 0,
        items: const <CircleImpactItemProjection>[],
      );
}

final class _CountingCircleGroupQuery implements CircleGroupQueryReader {
  const _CountingCircleGroupQuery();

  CircleGroupSlice _group(String circleId) => CircleGroupSlice(
    groupId: '${circleId}_group_default',
    version: 1,
    circleId: circleId,
    parentGroupId: null,
    groupType: CircleGroupType.publicGroup,
    nodeType: null,
    name: '默认公共群',
    description: '',
    visibility: CircleGroupVisibility.public,
    joinPolicy: CircleGroupJoinPolicy.applyOnly,
    conversationId: 'conversation_$circleId',
    storageEnabled: true,
    noticeEnabled: true,
    isDefaultPublicGroup: true,
    status: CircleGroupStatus.active,
    memberCount: 1,
    createdAt: DateTime.utc(2026, 7, 14),
    updatedAt: DateTime.utc(2026, 7, 14),
  );

  @override
  Future<CircleGroupSlice> get(CircleGroupQuery query) async =>
      _group(query.circleId);

  @override
  Future<CircleGroupPageSlice> list(CircleGroupListQuery query) async =>
      CircleGroupPageSlice(items: <CircleGroupSlice>[_group(query.circleId)]);

  @override
  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query) async =>
      CircleGroupPageSlice(items: <CircleGroupSlice>[_group(query.circleId)]);
}
