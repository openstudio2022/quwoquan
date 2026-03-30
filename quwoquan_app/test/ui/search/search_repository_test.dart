import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/integration/integration_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

void main() {
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
          profileSubjectId: 'user_001',
          ownerUserId: 'user_001',
          subAccountId: '',
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
            profileSubjectId: namespace.profileSubjectId,
            ownerUserId: namespace.ownerUserId,
            subAccountId: namespace.subAccountId,
            subjectType: namespace.subjectType,
            displayName: '测试用户',
            avatarUrl: '',
            personaContextVersion: namespace.personaContextVersion,
          );
        },
      );
    });

    tearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test('uses local contact filtering for suggest search', () async {
      final repo = AppSearchRepository(
        circleRepository: MockCircleRepository(),
        contentRepository: MockContentRepository(),
        homepageRepository: MockHomepageRepository(),
        integrationRepository: const MockIntegrationRepository(),
        localChatSearchStore: chatStore,
        localChatSearchSyncService: chatSyncService,
        localCircleGroupSnapshotStore: circleStore,
        personaContextLoader: () async {
          return ActivePersonaContextViewData.fallback(
            profileSubjectId: namespace.profileSubjectId,
            ownerUserId: namespace.ownerUserId,
            subAccountId: namespace.subAccountId,
            subjectType: namespace.subjectType,
            displayName: '测试用户',
            avatarUrl: '',
            personaContextVersion: namespace.personaContextVersion,
          );
        },
      );
      final query = (ChatMockData.contacts.first['displayName'] as String)
          .substring(0, 1);

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
      'falls back to local group results when remote returns empty',
      () async {
        final seedCircleId = CircleMockData.circles.first['id'] as String;
        final seedGroup = (await _EmptyCircleRepository().listCircleGroups(
          seedCircleId,
          limit: 1,
        )).first;
        final repo = AppSearchRepository(
          circleRepository: _EmptyCircleRepository(),
          contentRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          integrationRepository: const MockIntegrationRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              profileSubjectId: namespace.profileSubjectId,
              ownerUserId: namespace.ownerUserId,
              subAccountId: namespace.subAccountId,
              subjectType: namespace.subjectType,
              displayName: '测试用户',
              avatarUrl: '',
              personaContextVersion: namespace.personaContextVersion,
            );
          },
        );
        final query = (seedGroup['name'] as String).substring(0, 2);

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
          equals(SearchResolvedFrom.localFallback),
        );
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'circle_group_remote_empty',
          ),
          isTrue,
        );
      },
    );

    test(
      'falls back to persisted local group snapshot when remote search fails',
      () async {
        final seedCircleId = CircleMockData.circles.first['id'] as String;
        final seedGroup = (await MockCircleRepository().listCircleGroups(
          seedCircleId,
          limit: 1,
        )).first;
        await circleStore.upsertGroups(
          namespace: namespace,
          groups: <Map<String, dynamic>>[
            <String, dynamic>{
              ...seedGroup,
              'circleId': seedCircleId,
              'circleName': CircleMockData.circles.first['name'],
            },
          ],
        );
        final repo = AppSearchRepository(
          circleRepository: _ThrowingCircleRepository(),
          contentRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          integrationRepository: const MockIntegrationRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              profileSubjectId: namespace.profileSubjectId,
              ownerUserId: namespace.ownerUserId,
              subAccountId: namespace.subAccountId,
              subjectType: namespace.subjectType,
              displayName: '测试用户',
              avatarUrl: '',
              personaContextVersion: namespace.personaContextVersion,
            );
          },
        );
        final query = (seedGroup['name'] as String).substring(0, 2);

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
          equals(SearchResolvedFrom.localFallback),
        );
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'circle_group_remote_failed',
          ),
          isTrue,
        );
      },
    );

    test(
      'fails closed with degrade signals when circle fallback path has no cache',
      () async {
        final repo = AppSearchRepository(
          circleRepository: _ThrowingCircleRepository(),
          contentRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          integrationRepository: const MockIntegrationRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              profileSubjectId: namespace.profileSubjectId,
              ownerUserId: namespace.ownerUserId,
              subAccountId: namespace.subAccountId,
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
          isTrue,
        );
        expect(
          response.degradeSignals.any(
            (signal) => signal.code == 'circle_group_remote_failed',
          ),
          isTrue,
        );
      },
    );

    test(
      'fails closed when remote content and homepage providers throw',
      () async {
        final repo = AppSearchRepository(
          circleRepository: MockCircleRepository(),
          contentRepository: _ThrowingContentRepository(),
          homepageRepository: _ThrowingHomepageRepository(),
          integrationRepository: _ThrowingIntegrationRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              profileSubjectId: namespace.profileSubjectId,
              ownerUserId: namespace.ownerUserId,
              subAccountId: namespace.subAccountId,
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
        contentRepository: MockContentRepository(),
        homepageRepository: MockHomepageRepository(),
        integrationRepository: const MockIntegrationRepository(),
        localChatSearchStore: chatStore,
        localChatSearchSyncService: chatSyncService,
        localCircleGroupSnapshotStore: circleStore,
        personaContextLoader: () async {
          return ActivePersonaContextViewData.fallback(
            profileSubjectId: namespace.profileSubjectId,
            ownerUserId: namespace.ownerUserId,
            subAccountId: namespace.subAccountId,
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
          contentRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          integrationRepository: const MockIntegrationRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              profileSubjectId: namespace.profileSubjectId,
              ownerUserId: namespace.ownerUserId,
              subAccountId: namespace.subAccountId,
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
          contentRepository: MockContentRepository(),
          homepageRepository: MockHomepageRepository(),
          integrationRepository: const MockIntegrationRepository(),
          localChatSearchStore: chatStore,
          localChatSearchSyncService: chatSyncService,
          localCircleGroupSnapshotStore: circleStore,
          personaContextLoader: () async {
            return ActivePersonaContextViewData.fallback(
              profileSubjectId: namespace.profileSubjectId,
              ownerUserId: namespace.ownerUserId,
              subAccountId: namespace.subAccountId,
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

    test('isolates local chat results by namespace', () async {
      final repo = AppSearchRepository(
        circleRepository: MockCircleRepository(),
        contentRepository: MockContentRepository(),
        homepageRepository: MockHomepageRepository(),
        integrationRepository: const MockIntegrationRepository(),
        localChatSearchStore: chatStore,
        localChatSearchSyncService: chatSyncService,
        localCircleGroupSnapshotStore: circleStore,
        personaContextLoader: () async {
          return ActivePersonaContextViewData.fallback(
            profileSubjectId: namespace.profileSubjectId,
            ownerUserId: namespace.ownerUserId,
            subAccountId: namespace.subAccountId,
            subjectType: namespace.subjectType,
            displayName: '测试用户',
            avatarUrl: '',
            personaContextVersion: namespace.personaContextVersion,
          );
        },
      );
      final otherNamespace = LocalSearchNamespace.fromActivePersonaContext(
        ActivePersonaContextViewData.fallback(
          profileSubjectId: 'sub_002',
          ownerUserId: 'user_001',
          subAccountId: 'sub_002',
          subjectType: 'sub_account',
          displayName: '子账号',
          avatarUrl: '',
          personaContextVersion: 'v2',
        ),
      );
      await chatStore.upsertContacts(
        namespace: otherNamespace,
        contacts: <Map<String, dynamic>>[
          <String, dynamic>{
            'contactId': 'hidden_contact',
            'displayName': '隔离联系人',
          },
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

class _EmptyCircleRepository extends MockCircleRepository {
  @override
  Future<List<Map<String, dynamic>>> searchCircleGroups(
    String circleId, {
    required String query,
    String? visibility,
    String? groupType,
    int limit = 20,
  }) async {
    return const <Map<String, dynamic>>[];
  }
}

class _ThrowingCircleRepository extends MockCircleRepository {
  @override
  Future<List<Map<String, dynamic>>> listCircles({
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
  }) async {
    throw StateError('homepage unavailable');
  }
}

class _ThrowingIntegrationRepository extends MockIntegrationRepository {
  @override
  Future<List<LocationPoiDto>> searchLocations({
    required String query,
    String? cityCode,
    double? latitude,
    double? longitude,
    int limit = 20,
  }) async {
    throw StateError('location unavailable');
  }
}
