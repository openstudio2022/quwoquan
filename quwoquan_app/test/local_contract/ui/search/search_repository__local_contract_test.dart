import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_contact_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_record.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import '../../../support/fixtures/chat/chat_mock_seed_refs.dart';
import '../../../support/sqflite_ffi_test_support.dart';

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  group('AppSearchRepository', () {
    late Directory tempDir;
    late LocalSearchNamespace namespace;
    late LocalChatSearchStore chatStore;
    late LocalCircleGroupSnapshotStore circleStore;
    late LocalChatSearchSyncService chatSyncService;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('search_repo_test_');
      namespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          subAccountId: 'user_001',
          ownerUserId: 'user_001',
          subjectType: 'owner',
          displayName: '测试用户',
          avatarUrl: '',
          personaContextVersion: 'v1',
        ),
      );
      chatStore = LocalChatSearchStore(
        databasePath: '${tempDir.path}/chat_search.db',
      );
      circleStore = LocalCircleGroupSnapshotStore(
        databasePath: '${tempDir.path}/circle_groups.db',
      );
      chatSyncService = LocalChatSearchSyncService(
        chatRepository: MockChatRepository(),
        conversationCache: ConversationCacheService(),
        store: chatStore,
        personaContextLoader: () async {
          return ActivePersonaContextViewData.fallback(
            subAccountId: namespace.subAccountId,
            ownerUserId: namespace.ownerUserId,
            subjectType: namespace.subjectType,
            displayName: '测试用户',
            avatarUrl: '',
            personaContextVersion: namespace.personaContextVersion,
          );
        },
        telemetrySink: const NoopCacheTelemetrySink(),
      );
    });

    tearDown(() async {
      await chatSyncService.waitUntilIdle();
      await circleStore.waitUntilIdle();
      await chatStore.close();
      await circleStore.close();
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test('uses local contact filtering for suggest search', () async {
      await chatSyncService.sync(force: true);
      final repo = AppSearchRepository(
        circleRepository: MockCircleRepository(),
        circleGroupQuery: const _FixtureCircleGroupQuery(),
        contentPostSearchRepository: MockContentRepository(),
        homepageRepository: MockHomepageRepository(),
        locationSearchReader: const _FixtureLocationSearchReader(),
        userProfileRepository: const MockUserProfileRepository(),
        localChatSearchStore: chatStore,
        localChatSearchSyncService: chatSyncService,
        localCircleGroupSnapshotStore: circleStore,
        personaContextLoader: () async {
          return ActivePersonaContextViewData.fallback(
            subAccountId: namespace.subAccountId,
            ownerUserId: namespace.ownerUserId,
            subjectType: namespace.subjectType,
            displayName: '测试用户',
            avatarUrl: '',
            personaContextVersion: namespace.personaContextVersion,
          );
        },
      );
      final query = chatDisplayNameFor('user_002').substring(0, 1);

      final response = await repo.search(
        SearchRequest(
          query: query,
          mode: SearchMode.suggest,
          objectTypes: const <SearchObjectType>{SearchObjectType.chatContact},
        ),
      );

      expect(response.sections, isNotEmpty);
      expect(response.sections.first.id, equals('contacts'));
      expect(
        response.sections.first.hits.every(
          (hit) => hit.objectType == SearchObjectType.chatContact,
        ),
        isTrue,
      );
      expect(response.sections.first.resolvedFrom, SearchResolvedFrom.local);
    });

    test(
      'uses persisted local group results without waiting for remote search',
      () async {
        final seedCircleId = CircleMockData.catalogCircleDtos.first.id;
        final seedGroup = _fixtureCircleGroup(seedCircleId);
        await circleStore.upsertGroups(
          namespace: namespace,
          groups: <LocalCircleGroupSnapshotRecord>[
            LocalCircleGroupSnapshotRecord.fromGroupSlice(
              seedGroup,
              circleName: '本地回退圈子',
            ),
          ],
        );
        final repo = AppSearchRepository(
          circleRepository: MockCircleRepository(),
          circleGroupQuery: const _FixtureCircleGroupQuery(empty: true),
          contentPostSearchRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          locationSearchReader: const _FixtureLocationSearchReader(),
          userProfileRepository: const MockUserProfileRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              subAccountId: namespace.subAccountId,
              ownerUserId: namespace.ownerUserId,
              subjectType: namespace.subjectType,
              displayName: '测试用户',
              avatarUrl: '',
              personaContextVersion: namespace.personaContextVersion,
            );
          },
        );
        final query = seedGroup.name.substring(0, 2);

        final response = await repo.search(
          SearchRequest(
            query: query,
            mode: SearchMode.suggest,
            objectTypes: const <SearchObjectType>{SearchObjectType.circleGroup},
          ),
        );

        expect(response.sections, isNotEmpty);
        expect(response.sections.first.id, equals('groups'));
        expect(
          response.sections.first.resolvedFrom,
          equals(SearchResolvedFrom.local),
        );
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'circle_group_remote_empty',
          ),
          isFalse,
        );
      },
    );

    test(
      'does not invoke failing remote group search during suggestions',
      () async {
        final seedCircleId = CircleMockData.catalogCircleDtos.first.id;
        final seedGroup = _fixtureCircleGroup(seedCircleId);
        await circleStore.upsertGroups(
          namespace: namespace,
          groups: <LocalCircleGroupSnapshotRecord>[
            LocalCircleGroupSnapshotRecord.fromGroupSlice(
              seedGroup,
              circleName: CircleMockData.catalogCircleDtos.first.name,
            ),
          ],
        );
        final repo = AppSearchRepository(
          circleRepository: _ThrowingCircleRepository(),
          circleGroupQuery: const _FixtureCircleGroupQuery(),
          contentPostSearchRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          locationSearchReader: const _FixtureLocationSearchReader(),
          userProfileRepository: const MockUserProfileRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              subAccountId: namespace.subAccountId,
              ownerUserId: namespace.ownerUserId,
              subjectType: namespace.subjectType,
              displayName: '测试用户',
              avatarUrl: '',
              personaContextVersion: namespace.personaContextVersion,
            );
          },
        );
        final query = seedGroup.name.substring(0, 2);

        final response = await repo.search(
          SearchRequest(
            query: query,
            mode: SearchMode.suggest,
            objectTypes: const <SearchObjectType>{SearchObjectType.circleGroup},
          ),
        );

        expect(response.sections, isNotEmpty);
        expect(
          response.sections.first.resolvedFrom,
          equals(SearchResolvedFrom.local),
        );
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'circle_group_remote_failed',
          ),
          isFalse,
        );
      },
    );

    test(
      'settles an empty local group domain without waiting for background seed',
      () async {
        final repo = AppSearchRepository(
          circleRepository: _ThrowingCircleRepository(),
          circleGroupQuery: const _FixtureCircleGroupQuery(),
          contentPostSearchRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          locationSearchReader: const _FixtureLocationSearchReader(),
          userProfileRepository: const MockUserProfileRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              subAccountId: namespace.subAccountId,
              ownerUserId: namespace.ownerUserId,
              subjectType: namespace.subjectType,
              displayName: '测试用户',
              avatarUrl: '',
              personaContextVersion: namespace.personaContextVersion,
            );
          },
        );

        final response = await repo.search(
          const SearchRequest(
            query: '不存在的群组',
            mode: SearchMode.suggest,
            objectTypes: <SearchObjectType>{SearchObjectType.circleGroup},
          ),
        );

        expect(response.sections, isEmpty);
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'circle_group_snapshot_seed_failed',
          ),
          isFalse,
        );
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'circle_group_remote_failed',
          ),
          isFalse,
        );
      },
    );

    test(
      'fails closed when remote content and homepage providers throw',
      () async {
        final repo = AppSearchRepository(
          circleRepository: MockCircleRepository(),
          circleGroupQuery: const _FixtureCircleGroupQuery(),
          contentPostSearchRepository: _ThrowingContentRepository(),
          homepageRepository: _ThrowingHomepageRepository(),
          locationSearchReader: _ThrowingLocationSearchReader(),
          userProfileRepository: const MockUserProfileRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              subAccountId: namespace.subAccountId,
              ownerUserId: namespace.ownerUserId,
              subjectType: namespace.subjectType,
              displayName: '测试用户',
              avatarUrl: '',
              personaContextVersion: namespace.personaContextVersion,
            );
          },
        );

        final response = await repo.search(
          const SearchRequest(
            query: '深圳',
            mode: SearchMode.result,
            objectTypes: <SearchObjectType>{
              SearchObjectType.contentPost,
              SearchObjectType.entityHomepage,
            },
          ),
        );

        expect(response.sections, isEmpty);
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'content_remote_failed',
          ),
          isTrue,
        );
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'homepage_remote_failed',
          ),
          isTrue,
        );
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'location_remote_failed',
          ),
          isFalse,
        );
      },
    );

    test('returns circle.circle hits through groups section', () async {
      final repo = AppSearchRepository(
        circleRepository: MockCircleRepository(),
        circleGroupQuery: const _FixtureCircleGroupQuery(),
        contentPostSearchRepository: MockContentRepository(),
        homepageRepository: MockHomepageRepository(),
        locationSearchReader: const _FixtureLocationSearchReader(),
        userProfileRepository: const MockUserProfileRepository(),
        localChatSearchStore: chatStore,
        localChatSearchSyncService: chatSyncService,
        localCircleGroupSnapshotStore: circleStore,
        personaContextLoader: () async {
          return ActivePersonaContextViewData.fallback(
            subAccountId: namespace.subAccountId,
            ownerUserId: namespace.ownerUserId,
            subjectType: namespace.subjectType,
            displayName: '测试用户',
            avatarUrl: '',
            personaContextVersion: namespace.personaContextVersion,
          );
        },
      );

      final response = await repo.search(
        const SearchRequest(
          query: '光影',
          mode: SearchMode.result,
          objectTypes: <SearchObjectType>{SearchObjectType.circleCircle},
        ),
      );

      expect(response.sections, isNotEmpty);
      expect(response.sections.first.id, equals('groups'));
      expect(
        response.sections.first.hits.any(
          (hit) => hit.objectType == SearchObjectType.circleCircle,
        ),
        isTrue,
      );
    });

    test(
      'returns mixed group coverage when group and circle types requested',
      () async {
        final repo = AppSearchRepository(
          circleRepository: MockCircleRepository(),
          circleGroupQuery: const _FixtureCircleGroupQuery(),
          contentPostSearchRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          locationSearchReader: const _FixtureLocationSearchReader(),
          userProfileRepository: const MockUserProfileRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              subAccountId: namespace.subAccountId,
              ownerUserId: namespace.ownerUserId,
              subjectType: namespace.subjectType,
              displayName: '测试用户',
              avatarUrl: '',
              personaContextVersion: namespace.personaContextVersion,
            );
          },
        );

        final response = await repo.search(
          const SearchRequest(
            query: '光影',
            mode: SearchMode.result,
            objectTypes: <SearchObjectType>{
              SearchObjectType.circleGroup,
              SearchObjectType.circleCircle,
            },
          ),
        );

        expect(response.sections, isNotEmpty);
        expect(response.sections.first.id, equals('groups'));
        expect(response.hits, isNotEmpty);
      },
    );

    test(
      'returns integration.location_poi hits through locations section',
      () async {
        final repo = AppSearchRepository(
          circleRepository: MockCircleRepository(),
          circleGroupQuery: const _FixtureCircleGroupQuery(),
          contentPostSearchRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          locationSearchReader: const _FixtureLocationSearchReader(),
          userProfileRepository: const MockUserProfileRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              subAccountId: namespace.subAccountId,
              ownerUserId: namespace.ownerUserId,
              subjectType: namespace.subjectType,
              displayName: '测试用户',
              avatarUrl: '',
              personaContextVersion: namespace.personaContextVersion,
            );
          },
        );

        final response = await repo.search(
          const SearchRequest(
            query: '西湖',
            mode: SearchMode.result,
            objectTypes: <SearchObjectType>{
              SearchObjectType.integrationLocationPoi,
            },
          ),
        );

        expect(response.sections, isNotEmpty);
        expect(response.sections.first.id, equals('locations'));
        expect(
          response.sections.first.hits.first.objectType,
          equals(SearchObjectType.integrationLocationPoi),
        );
        expect(response.sections.first.hits.first.title, contains('西湖'));
      },
    );

    test('returns location.place hits through locations section', () async {
      final repo = AppSearchRepository(
        circleRepository: MockCircleRepository(),
        circleGroupQuery: const _FixtureCircleGroupQuery(),
        contentPostSearchRepository: MockContentRepository(),
        homepageRepository: MockHomepageRepository(),
        locationSearchReader: const _FixtureLocationSearchReader(),
        userProfileRepository: const MockUserProfileRepository(),
        localChatSearchStore: chatStore,
        localChatSearchSyncService: chatSyncService,
        localCircleGroupSnapshotStore: circleStore,
        personaContextLoader: () async {
          return ActivePersonaContextViewData.fallback(
            subAccountId: namespace.subAccountId,
            ownerUserId: namespace.ownerUserId,
            subjectType: namespace.subjectType,
            displayName: '测试用户',
            avatarUrl: '',
            personaContextVersion: namespace.personaContextVersion,
          );
        },
      );

      final response = await repo.search(
        const SearchRequest(
          query: '西湖',
          mode: SearchMode.result,
          objectTypes: <SearchObjectType>{SearchObjectType.locationPlace},
        ),
      );

      expect(response.sections, isNotEmpty);
      expect(response.sections.first.id, equals('locations'));
      expect(
        response.sections.first.hits.first.objectType,
        equals(SearchObjectType.locationPlace),
      );
      expect(response.sections.first.hits.first.title, contains('西湖'));
    });

    test('isolates local chat results by namespace', () async {
      final repo = AppSearchRepository(
        circleRepository: MockCircleRepository(),
        circleGroupQuery: const _FixtureCircleGroupQuery(),
        contentPostSearchRepository: MockContentRepository(),
        homepageRepository: MockHomepageRepository(),
        locationSearchReader: const _FixtureLocationSearchReader(),
        userProfileRepository: const MockUserProfileRepository(),
        localChatSearchStore: chatStore,
        localChatSearchSyncService: chatSyncService,
        localCircleGroupSnapshotStore: circleStore,
        personaContextLoader: () async {
          return ActivePersonaContextViewData.fallback(
            subAccountId: namespace.subAccountId,
            ownerUserId: namespace.ownerUserId,
            subjectType: namespace.subjectType,
            displayName: '测试用户',
            avatarUrl: '',
            personaContextVersion: namespace.personaContextVersion,
          );
        },
      );
      final otherNamespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          subAccountId: 'sub_002',
          ownerUserId: 'user_001',
          subjectType: 'sub_account',
          displayName: '子账号',
          avatarUrl: '',
          personaContextVersion: 'v2',
        ),
      );
      await chatStore.upsertContacts(
        namespace: otherNamespace,
        contacts: const <LocalChatSearchContactRecord>[
          LocalChatSearchContactRecord(
            contactId: 'hidden_contact',
            displayName: '隔离联系人',
          ),
        ],
      );

      final response = await repo.search(
        const SearchRequest(
          query: '隔离',
          mode: SearchMode.suggest,
          objectTypes: <SearchObjectType>{SearchObjectType.chatContact},
        ),
      );

      expect(response.sections, isEmpty);
      expect(
        response.degradeSignals.any(
          (signal) => signal.code == 'chat_local_contact_miss',
        ),
        isTrue,
      );
    });
  });
}

class _ThrowingCircleRepository extends MockCircleRepository {
  @override
  Future<List<CircleDto>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
  }) async {
    throw StateError('circle unavailable');
  }
}

CircleGroupSlice _fixtureCircleGroup(String circleId) => CircleGroupSlice(
  groupId: '${circleId}_group_default',
  version: 1,
  circleId: circleId,
  parentGroupId: null,
  groupType: CircleGroupType.publicGroup,
  nodeType: null,
  name: '默认公开群',
  description: '圈子默认群组',
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

final class _FixtureCircleGroupQuery implements CircleGroupQueryReader {
  const _FixtureCircleGroupQuery({this.empty = false});
  final bool empty;

  @override
  Future<CircleGroupSlice> get(CircleGroupQuery query) async =>
      _fixtureCircleGroup(query.circleId);

  @override
  Future<CircleGroupPageSlice> list(CircleGroupListQuery query) async =>
      CircleGroupPageSlice(
        items: empty
            ? const <CircleGroupSlice>[]
            : <CircleGroupSlice>[_fixtureCircleGroup(query.circleId)],
      );

  @override
  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query) async {
    if (empty) return const CircleGroupPageSlice(items: <CircleGroupSlice>[]);
    final group = _fixtureCircleGroup(query.circleId);
    return CircleGroupPageSlice(
      items: group.name.contains(query.query)
          ? <CircleGroupSlice>[group]
          : const <CircleGroupSlice>[],
    );
  }
}

class _ThrowingContentRepository extends MockContentRepository {
  @override
  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = 20,
  }) async {
    throw StateError('content unavailable');
  }
}

class _ThrowingHomepageRepository extends MockHomepageRepository {
  @override
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = 20,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    throw StateError('homepage unavailable');
  }
}

class _FixtureLocationSearchReader implements LocationSearchReader {
  const _FixtureLocationSearchReader();

  @override
  Future<LocationPoiListSlice> searchLocations(
    LocationSearchQueryParams query,
  ) async {
    final items = <LocationPoiDto>[
      LocationPoiDto(
        id: 'fixture_poi_west_lake',
        name: '杭州西湖',
        latitude: 30.2431,
        longitude: 120.1505,
        address: '浙江省杭州市西湖区',
      ),
    ];
    final normalized = query.query.trim();
    return LocationPoiListSlice(
      items
          .where(
            (item) =>
                normalized.isEmpty ||
                item.name.contains(normalized) ||
                (item.address ?? '').contains(normalized),
          )
          .take(query.limit)
          .toList(growable: false),
    );
  }
}

class _ThrowingLocationSearchReader implements LocationSearchReader {
  @override
  Future<LocationPoiListSlice> searchLocations(
    LocationSearchQueryParams query,
  ) async {
    throw StateError('location unavailable');
  }
}
