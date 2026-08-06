// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/local-search-lifecycle-and-account-isolation/spec.md#gwt-001
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_group_local_search.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/local_circle_group_search_index.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/local_circle_group_snapshot_record.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/conversation_avatar_search_index.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_contract_test_builders.dart';
import '../../../../../support/runtime/platform/explicit_test_local_database_path_resolver.dart';

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  group('LocalCircleGroupSnapshotStore', () {
    late Directory tempDir;
    late LocalCircleGroupSnapshotStore store;
    late CircleLocalSearchScope ownerNamespace;
    late CircleLocalSearchScope subNamespace;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp(
        'local_circle_snapshot_test_',
      );
      store = LocalCircleGroupSnapshotStore(
        databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
        databasePath: '${tempDir.path}/circle_groups.db',
      );
      ownerNamespace = const CircleLocalSearchScope(
        personaId: 'user_owner',
        ownerUserId: 'user_owner',
        subjectType: 'owner',
        personaContextVersion: '1',
      );
      subNamespace = const CircleLocalSearchScope(
        personaId: 'sub_001',
        ownerUserId: 'user_owner',
        subjectType: 'persona',
        personaContextVersion: '2',
      );
      await store.ensureReady();
    });

    tearDown(() async {
      await store.close();
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

    test('搜索索引在同一账号同步窗口内只刷新一次', () async {
      final reader = _CountingCircleQueryReader();
      final index = SqfliteLocalCircleGroupSearchIndex(
        store,
        () async => const SearchActorScope(
          personaId: 'user_owner',
          ownerUserId: 'user_owner',
          subjectType: 'owner',
          personaContextVersion: '1',
        ),
        reader,
        const _CountingCircleGroupQuery(),
      );

      expect(await index.sync(), isTrue);
      expect(await index.sync(), isTrue);
      expect(reader.listCalls, 1);
      expect(await index.searchGroups(query: '默认'), hasLength(1));
    });

    test('forceRefresh 原子替换快照并清除已退出讨论', () async {
      await store.upsertGroups(
        namespace: ownerNamespace,
        groups: const <LocalCircleGroupSnapshotRecord>[
          LocalCircleGroupSnapshotRecord(
            circleId: 'fixture_circle_photo',
            groupId: 'stale_group',
            name: '已退出摄影讨论',
            description: '过期数据',
            circleName: '契约摄影社',
            groupType: 'public_group',
            visibility: 'public',
            updatedAt: '2026-07-13T00:00:00.000Z',
          ),
        ],
      );

      await store.ensureSeeded(
        namespace: ownerNamespace,
        circleQuery: _CountingCircleQueryReader(),
        circleGroupQuery: const _CountingCircleGroupQuery(groupName: '最新摄影讨论'),
        forceRefresh: true,
      );

      expect(
        await store.searchGroups(namespace: ownerNamespace, query: '已退出'),
        isEmpty,
      );
      expect(
        await store.searchGroups(namespace: ownerNamespace, query: '最新'),
        hasLength(1),
      );
    });

    test('账号 closed 终态物理清除全部 namespace', () async {
      const snapshot = LocalCircleGroupSnapshotRecord(
        circleId: 'circle_terminal',
        groupId: 'group_terminal',
        name: '终态清理群',
        description: 'local residual',
        circleName: '终态圈',
        groupType: 'public_group',
        visibility: 'public',
        updatedAt: '2026-07-24T00:00:00.000Z',
      );
      await store.upsertGroups(
        namespace: ownerNamespace,
        groups: const <LocalCircleGroupSnapshotRecord>[snapshot],
      );
      await store.upsertGroups(
        namespace: subNamespace,
        groups: const <LocalCircleGroupSnapshotRecord>[snapshot],
      );

      await store.clearAllNamespaces();

      expect(await store.hasAnySnapshot(ownerNamespace), isFalse);
      expect(await store.hasAnySnapshot(subNamespace), isFalse);
    });

    test('seed 读取失败时显式失败且不提交不完整快照', () async {
      final reader = _CountingCircleQueryReader();
      final failure = StateError('circle group query unavailable');

      await expectLater(
        store.ensureSeeded(
          namespace: ownerNamespace,
          circleQuery: reader,
          circleGroupQuery: _CountingCircleGroupQuery(failure: failure),
        ),
        throwsA(same(failure)),
      );

      expect(await store.hasAnySnapshot(ownerNamespace), isFalse);
    });

    test('forceRefresh 读取失败时保留上一份完整快照', () async {
      await store.upsertGroups(
        namespace: ownerNamespace,
        groups: const <LocalCircleGroupSnapshotRecord>[
          LocalCircleGroupSnapshotRecord(
            circleId: 'fixture_circle_photo',
            groupId: 'stable_group',
            name: '保留摄影讨论',
            description: '上一份完整快照',
            circleName: '契约摄影社',
            groupType: 'public_group',
            visibility: 'public',
            updatedAt: '2026-07-13T00:00:00.000Z',
          ),
        ],
      );
      final failure = StateError('circle group query unavailable');

      await expectLater(
        store.ensureSeeded(
          namespace: ownerNamespace,
          circleQuery: _CountingCircleQueryReader(),
          circleGroupQuery: _CountingCircleGroupQuery(failure: failure),
          forceRefresh: true,
        ),
        throwsA(same(failure)),
      );

      expect(
        await store.searchGroups(namespace: ownerNamespace, query: '保留'),
        hasLength(1),
      );
    });
  });
}

final class _CountingCircleQueryReader implements CircleQueryReader {
  int listCalls = 0;

  @override
  Future<CirclePageSlice> list(CircleListQuery query) async {
    listCalls += 1;
    return CirclePageSlice(
      items: <Circle>[
        buildCircleContract(
          circleId: 'fixture_circle_photo',
          name: '契约摄影社',
          ownerId: 'fixture_owner',
        ),
      ],
    );
  }

  @override
  Future<CircleSearchResultView> search(CircleSearchQuery query) async =>
      CircleSearchResultView(
        items: const <CircleSearchItemView>[],
        facetBuckets: const <CircleFacetBucketView>[],
      );

  @override
  Future<Circle> get(CircleDetailQuery query) async =>
      throw UnimplementedError();

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query) async =>
      CircleFeedPageSlice(items: const <CircleFeedItemView>[]);

  @override
  Future<CircleStatsWire> stats(CircleStatsQuery query) async =>
      buildCircleStatsContract(circleId: query.circleId);

  @override
  Future<CircleImpactSummary> impact(CircleImpactQuery query) async =>
      CircleImpactSummary(
        circleId: query.circleId,
        total: 0,
        items: const <CircleImpactItem>[],
      );
}

final class _CountingCircleGroupQuery implements CircleGroupQueries {
  const _CountingCircleGroupQuery({this.failure, this.groupName = '默认公共群'});

  final Object? failure;
  final String groupName;

  CircleGroupSlice _group(String circleId) => CircleGroupSlice(
    groupId: '${circleId}_group_default',
    version: 1,
    circleId: circleId,
    parentGroupId: null,
    groupType: CircleGroupType.publicGroup,
    nodeType: null,
    name: groupName,
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
  Future<CircleGroupPageSlice> list(CircleGroupListQuery query) async {
    if (failure != null) {
      throw failure!;
    }
    return CircleGroupPageSlice(
      items: <CircleGroupSlice>[_group(query.circleId)],
    );
  }

  @override
  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query) async =>
      CircleGroupPageSlice(items: <CircleGroupSlice>[_group(query.circleId)]);
}
