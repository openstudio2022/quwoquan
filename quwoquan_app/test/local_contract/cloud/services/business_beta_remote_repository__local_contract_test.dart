import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/chat/chat/conversation/adapters/contact_remote.dart';
import 'package:quwoquan_app/chat/chat/conversation/adapters/conversation_membership_remote.dart';
import 'package:quwoquan_app/chat/chat/conversation/adapters/conversation_remote.dart';
import 'package:quwoquan_app/chat/chat/conversation/adapters/conversation_user_state_remote.dart';
import 'package:quwoquan_app/chat/chat/conversation/adapters/message_home_remote.dart';
import 'package:quwoquan_app/chat/chat/message/adapters/message_remote.dart';
import 'package:quwoquan_app/circle/circle_management/circle/adapters/circle_query_remote.dart';
import 'package:quwoquan_app/cloud/services/chat/remote/chat_repository_remote.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/content/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_app/content/content/feed_delivery_page/adapters/discovery_feed_query_remote.dart';
import 'package:quwoquan_app/content/content/post/adapters/post_reader_remote.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/user/persona_management/persona/adapters/persona_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/profile_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/user_profile_query_remote.dart';
import 'package:quwoquan_app/content/content/post/domain/content_surface_view_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentType;

final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');

void main() {
  test('beta object Facets read contract fixture data through HTTP', () async {
    final fixtures = _BusinessFixtures.load();
    final server = await _ContractSeedHttpServer.start(fixtures);
    addTearDown(server.close);

    final baseUrl = 'http://${server.address.host}:${server.port}';
    final httpClient = CloudHttpClient(
      authTokenProvider: const _BusinessFixtureAuthTokenProvider(),
    );
    final generatedClient = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: const _BusinessFixtureClientContext(),
      telemetrySink: const _NoopCloudOperationTelemetrySink(),
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.beta,
        gatewayBaseUri: Uri.parse(baseUrl),
      ),
    );
    final contentRepository = RemoteContentRepository(
      discoveryFeedQuery: RemoteContentDiscoveryFeedQuery(
        client: generatedClient,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.homeFeed.id,
          routeId: AppUiSurfaces.homeFeed.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
        blockedKeywordsLoader: () async => const <String>[],
      ),
    );
    final contentPostReader = RemoteContentPostReaderAdapter(
      client: generatedClient,
      invocationContext: (clientPageId) {
        final surface = clientPageId == ContentRequestPageIds.listUserPosts
            ? AppUiSurfaces.userProfile
            : AppUiSurfaces.workBrowser;
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        );
      },
    );
    const currentUserId = 'fixture_user_current';
    CloudOperationInvocationContext chatContext(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    }) {
      return CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(
          accountId: currentUserId,
          personaId: currentUserId,
        ),
        idempotencyKey: idempotencyKey,
      );
    }

    final conversationQuery = RemoteChatConversationQuery(
      client: generatedClient,
      invocationContext: (clientPageId) =>
          chatContext(AppUiSurfaces.chatList, clientPageId),
    );
    final contactQuery = RemoteChatContactQuery(
      client: generatedClient,
      invocationContext: (clientPageId) =>
          chatContext(AppUiSurfaces.chatList, clientPageId),
    );
    final membershipQuery = RemoteChatConversationMembershipQuery(
      client: generatedClient,
      invocationContext: (clientPageId) =>
          chatContext(AppUiSurfaces.chatManage, clientPageId),
    );
    final chatRepository = RemoteChatRepository(
      conversationQuery: conversationQuery,
      conversationCommandWriter: RemoteChatConversationCommandWriter(
        client: generatedClient,
        invocationContext: (clientPageId, idempotencyKey) => chatContext(
          AppUiSurfaces.chatManage,
          clientPageId,
          idempotencyKey: idempotencyKey,
        ),
      ),
      contactQuery: contactQuery,
      inboxQuery: contactQuery,
      messageHomeQuery: RemoteChatMessageHomeQuery(
        client: generatedClient,
        invocationContext: (clientPageId) =>
            chatContext(AppUiSurfaces.chatList, clientPageId),
      ),
      membershipQuery: membershipQuery,
      membershipCommandWriter: RemoteChatConversationMembershipCommandWriter(
        client: generatedClient,
        invocationContext: (clientPageId, idempotencyKey) => chatContext(
          AppUiSurfaces.chatSettings,
          clientPageId,
          idempotencyKey: idempotencyKey,
        ),
      ),
      userStateCommandWriter: RemoteChatConversationUserStateCommandWriter(
        client: generatedClient,
        invocationContext: (clientPageId, idempotencyKey) => chatContext(
          AppUiSurfaces.chatDetail,
          clientPageId,
          idempotencyKey: idempotencyKey,
        ),
      ),
      messageQuery: RemoteChatMessageQuery(
        client: generatedClient,
        invocationContext: (clientPageId) =>
            chatContext(AppUiSurfaces.chatDetail, clientPageId),
      ),
      messageMutationWriter: RemoteChatMessageMutationWriter(
        client: generatedClient,
        invocationContext: (clientPageId, idempotencyKey) => chatContext(
          AppUiSurfaces.chatDetail,
          clientPageId,
          idempotencyKey: idempotencyKey,
        ),
      ),
    );
    final circleQuery = RemoteCircleQueryReader(
      client: generatedClient,
      invocationContext: (clientPageId, {required command}) {
        final surface =
            clientPageId == CircleRequestPageIds.listCircles ||
                clientPageId == CircleRequestPageIds.searchCircles ||
                clientPageId == CircleRequestPageIds.listCircleDiscoveryFeed
            ? AppUiSurfaces.circlesList
            : AppUiSurfaces.circleDetail;
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: currentUserId,
            personaId: currentUserId,
          ),
        );
      },
    );
    final userProfileQuery = RemoteUserProfileQueryFacet(
      client: generatedClient,
      invocationContext: (clientPageId, canonicalOperationId) {
        final operation = appCloudOperationContracts[canonicalOperationId]!;
        final surface = AppUiSurfaces.byId[operation.surfaceIds.first]!;
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: currentUserId,
            personaId: currentUserId,
          ),
        );
      },
    );
    final personaQuery = RemotePersonaQuery(
      managementQuery: userProfileQuery,
      publicProfileQuery: userProfileQuery,
    );
    final profileQuery = RemoteProfileQuery(
      publicProfileQuery: userProfileQuery,
      userHomepageQuery: userProfileQuery,
    );

    final photoFeed = await contentRepository.listDiscoveryFeed(
      category: 'photo',
      identity: 'work',
      type: 'photo',
      limit: 20,
    );
    expect(photoFeed.length, greaterThanOrEqualTo(3));
    expect(photoFeed.map((item) => item.id), contains('fixture_photo_001'));
    expect(
      photoFeed.every(
        (item) => item.primaryVisualUrl.contains(
          'media/image/s/archived-image/post/',
        ),
      ),
      isTrue,
    );
    final videoFeed = await contentRepository.listDiscoveryFeed(
      category: 'video',
      identity: 'work',
      type: 'video',
      limit: 20,
    );
    expect(videoFeed.length, greaterThanOrEqualTo(2));
    expect(videoFeed.every((item) => item.hasVideo), isTrue);
    final followingFeed = await contentRepository.listDiscoveryFeed(
      category: 'following',
      identity: 'moment',
      limit: 20,
    );
    expect(followingFeed.length, greaterThanOrEqualTo(3));
    final post = await contentPostReader.getPost(postId: 'fixture_photo_001');
    expect(post.post.id, 'fixture_photo_001');

    final inbox = await chatRepository.listInbox(limit: 20);
    expect(inbox.length, greaterThanOrEqualTo(5));
    expect(inbox.map((item) => item.id), contains('fixture_conv_direct'));
    expect(inbox.every((item) => item.avatarUrl.trim().isNotEmpty), isTrue);
    final messages = await chatRepository.listMessages(
      conversationId: 'fixture_conv_direct',
      limit: 20,
    );
    expect(messages.map((item) => item.id), contains('fixture_msg_direct_1'));
    final contacts = await chatRepository.listContacts(limit: 20);
    expect(contacts.items.length, greaterThanOrEqualTo(6));
    expect(
      contacts.items.map((item) => item.userId),
      contains('fixture_user_friend'),
    );
    final contactStates = contacts.items
        .map((item) => item.relationState)
        .toSet();
    expect(contactStates, contains('mutual'));
    expect(contactStates, isNot(contains('not_following')));
    expect(contacts.items.every((item) => item.source.isNotEmpty), isTrue);
    expect(
      contacts.items.every(
        (item) => item.avatarUrl.toLowerCase().startsWith('media/avatar/'),
      ),
      isTrue,
    );

    final messageHome = await chatRepository.listMessageHome(limit: 20);
    expect(messageHome.length, greaterThanOrEqualTo(5));
    expect(
      messageHome.every(
        (row) => row.avatarUrl.toLowerCase().startsWith('media/avatar/'),
      ),
      isTrue,
    );
    expect(messageHome.any((row) => row.mentionUnreadCount > 0), isTrue);

    final contactHomeAll = await chatRepository.listContactHome(
      filter: 'all',
      limit: 50,
    );
    expect(contactHomeAll.where((row) => row.kind == 'user'), isNotEmpty);
    expect(contactHomeAll.where((row) => row.kind == 'circle'), isNotEmpty);
    expect(
      contactHomeAll.every(
        (row) =>
            row.avatarUrl.isEmpty ||
            row.avatarUrl.toLowerCase().startsWith('media/avatar/'),
      ),
      isTrue,
    );

    final contactHomeCircles = await chatRepository.listContactHome(
      filter: 'circle',
      limit: 20,
    );
    expect(contactHomeCircles, isNotEmpty);
    expect(contactHomeCircles.every((row) => row.kind == 'circle'), isTrue);
    final groupMembers = await chatRepository.listMembers(
      conversationId: 'fixture_conv_group',
      limit: 20,
    );
    final contactIds = contacts.items.map((item) => item.userId).toSet();
    expect(
      groupMembers
          .where((member) => !member.isCurrentUser)
          .every((member) => contactIds.contains(member.userId)),
      isTrue,
    );
    expect(
      contactHomeCircles.map((item) => item.id),
      contains('fixture_circle_photo'),
    );
    final funGroups = await chatRepository.listContactHome(
      filter: 'group',
      limit: 20,
    );
    expect(
      funGroups.map((item) => item.conversationId),
      contains('fixture_conv_group'),
    );

    final circles = (await circleQuery.list(
      const CircleListQuery(limit: 20),
    )).items;
    expect(circles.length, greaterThanOrEqualTo(6));
    expect(
      circles.map((item) => item.id),
      contains('fixture_circle_photo'),
    );
    expect(
      circles.every(
        (item) =>
            item.coverUrl?.contains('media/image/s/archived-image/circle/') ==
            true,
      ),
      isTrue,
    );
    final circle = await circleQuery.get(
      const CircleDetailQuery(circleId: 'fixture_circle_photo'),
    );
    expect(circle.id, 'fixture_circle_photo');
    await expectLater(
      circleQuery.listDiscoveryFeed(const CircleDiscoveryFeedQuery(limit: 20)),
      throwsA(
        isA<CloudException>().having(
          (error) => error.runtimeFailure,
          'runtimeFailure',
          isNotNull,
        ),
      ),
    );

    final currentUser = await profileQuery.getUserProfile(
      'fixture_user_current',
    );
    final activePersonaContext = await personaQuery.getActivePersonaContext();
    expect(activePersonaContext.ownerUserId, currentUserId);
    expect(activePersonaContext.personaId, currentUserId);
    expect(currentUser.displayName, matches(_defaultNicknamePattern));
    final imageBase = CloudRuntimeConfig.mediaImageCdnBaseUrl.trim();
    if (imageBase.isEmpty) {
      expect(
        currentUser.backgroundUrl,
        isEmpty,
        reason: '未注入媒体交付 endpoint 时，不得把 object key 当作可加载 URL',
      );
    } else {
      expect(
        currentUser.backgroundUrl,
        startsWith('${Uri.parse(imageBase).origin}/media/background/'),
        reason: 'background 复用 mediaImage origin，路径只由 publicSliceKey 决定',
      );
    }
    final userPostsPage = await contentPostReader.listUserPosts(
      userId: 'fixture_user_current',
      limit: 20,
    );
    final userPosts = userPostsPage.items;
    expect(userPosts.length, greaterThanOrEqualTo(4));
    expect(userPosts.map((item) => item.id), contains('fixture_moment_001'));
    final moment = userPosts.firstWhere(
      (item) => item.id == 'fixture_moment_001',
    );
    final unavailableMediaResolver = MediaDeliveryResolver(
      MediaEndpointConfig.tryCreateAvailable(
        avatarBaseUrl: '',
        imageBaseUrl: '',
        videoBaseUrl: '',
        attachmentBaseUrl: '',
      )!,
    );
    final momentView = ContentSurfaceViewMapper.fromDto(
      moment,
      mediaResolver: unavailableMediaResolver,
    );
    expect(
      momentView.cover,
      isNull,
      reason: '未注入媒体交付 endpoint 时，不得把 post object key 当作可加载 URL',
    );
    expect(momentView.images, isEmpty);
    final userProfiles = await _getJsonList('$baseUrl/user/profile', 'items');
    expect(
      userProfiles.map((item) => item['userId']),
      contains('fixture_user_current'),
    );

    final homepages = await _getJsonList('$baseUrl/homepages/search', 'items');
    expect(
      homepages.map((item) => item['homepageId']),
      contains('fixture_homepage_author'),
    );

    final pois = await _getJsonList(
      '$baseUrl/integration/external_integration/locations/pois',
      'items',
    );
    expect(
      pois.map((item) => item['poiId']),
      contains('fixture_poi_west_lake'),
    );

    final appMessages = await _getJsonList('$baseUrl/app-messages', 'items');
    expect(
      appMessages.map((item) => item['messageId']),
      contains('fixture_app_message_assistant_stock'),
    );

    final calls = await _getJsonList('$baseUrl/rtc/calls', 'items');
    final expectedRtcSessionId =
        ((fixtures.rtcSeed['sessions'] as List<dynamic>).first
                as Map<String, dynamic>)['sessionId']
            as String;
    expect(
      calls.map((item) => item['sessionId']),
      contains(expectedRtcSessionId),
    );
  });
}

Future<List<Map<String, dynamic>>> _getJsonList(String url, String key) async {
  final client = HttpClient();
  try {
    final req = await client.getUrl(Uri.parse(url));
    final resp = await req.close();
    final body = await utf8.decodeStream(resp);
    expect(resp.statusCode, HttpStatus.ok);
    final decoded = json.decode(body) as Map<String, dynamic>;
    return ((decoded[key] as List?) ?? const <dynamic>[])
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
  } finally {
    client.close(force: true);
  }
}

class _BusinessFixtures {
  _BusinessFixtures({
    required this.contentSeed,
    required this.chatSeed,
    required this.chatContactsSeed,
    required this.circleSeed,
    required this.circleHomeSeed,
    required this.userSeed,
    required this.userFeedSeed,
    required this.entitySeed,
    required this.integrationSeed,
    required this.notificationSeed,
    required this.rtcSeed,
  });

  final Map<String, dynamic> contentSeed;
  final Map<String, dynamic> chatSeed;
  final Map<String, dynamic> chatContactsSeed;
  final Map<String, dynamic> circleSeed;
  final Map<String, dynamic> circleHomeSeed;
  final Map<String, dynamic> userSeed;
  final Map<String, dynamic> userFeedSeed;
  final Map<String, dynamic> entitySeed;
  final Map<String, dynamic> integrationSeed;
  final Map<String, dynamic> notificationSeed;
  final Map<String, dynamic> rtcSeed;

  static _BusinessFixtures load() {
    final content = _loadFixture(
      '../quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.json',
    );
    final chat = _loadFixture(
      '../quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.json',
    );
    final circle = _loadFixture(
      '../quwoquan_service/services/circle-service/tests/support/contract_fixtures/scenarios/circle_scenarios.json',
    );
    final user = _loadFixture(
      '../quwoquan_service/services/user-service/tests/support/contract_fixtures/scenarios/user_scenarios.json',
    );
    final entity = _loadFixture(
      '../quwoquan_service/services/entity-service/tests/support/contract_fixtures/scenarios/entity_scenarios.json',
    );
    final integration = _loadFixture(
      '../quwoquan_service/services/integration-service/tests/support/contract_fixtures/scenarios/integration_scenarios.json',
    );
    final notification = _loadFixture(
      '../quwoquan_service/services/notification-service/tests/support/contract_fixtures/scenarios/notification_scenarios.json',
    );
    final rtc = _loadFixture(
      '../quwoquan_service/services/rtc-service/tests/support/contract_fixtures/scenarios/rtc_scenarios.json',
    );
    return _BusinessFixtures(
      contentSeed:
          (content['seedSets']
                  as Map<String, dynamic>)['content_discovery_core']
              as Map<String, dynamic>,
      chatSeed:
          (chat['seedSets'] as Map<String, dynamic>)['chat_core']
              as Map<String, dynamic>,
      chatContactsSeed:
          (chat['seedSets'] as Map<String, dynamic>)['chat_contacts_core']
              as Map<String, dynamic>,
      circleSeed:
          (circle['seedSets'] as Map<String, dynamic>)['circle_core']
              as Map<String, dynamic>,
      circleHomeSeed:
          (circle['seedSets'] as Map<String, dynamic>)['circle_home_feed_core']
              as Map<String, dynamic>,
      userSeed:
          (user['seedSets'] as Map<String, dynamic>)['user_profile_core']
              as Map<String, dynamic>,
      userFeedSeed:
          (user['seedSets'] as Map<String, dynamic>)['profile_feed_core']
              as Map<String, dynamic>,
      entitySeed:
          (entity['seedSets'] as Map<String, dynamic>)['entity_homepage_core']
              as Map<String, dynamic>,
      integrationSeed:
          (integration['seedSets'] as Map<String, dynamic>)['location_poi_core']
              as Map<String, dynamic>,
      notificationSeed:
          (notification['seedSets']
                  as Map<String, dynamic>)['notification_core']
              as Map<String, dynamic>,
      rtcSeed:
          (rtc['seedSets'] as Map<String, dynamic>)['rtc_core']
              as Map<String, dynamic>,
    );
  }

  static Map<String, dynamic> _loadFixture(String path) {
    return json.decode(File(path).readAsStringSync()) as Map<String, dynamic>;
  }
}

class _ContractSeedHttpServer {
  _ContractSeedHttpServer._(this._server, this._fixtures);

  final HttpServer _server;
  final _BusinessFixtures _fixtures;

  InternetAddress get address => _server.address;
  int get port => _server.port;

  static Future<_ContractSeedHttpServer> start(
    _BusinessFixtures fixtures,
  ) async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final wrapper = _ContractSeedHttpServer._(server, fixtures);
    wrapper._serve();
    return wrapper;
  }

  Future<void> close() => _server.close(force: true);

  void _serve() {
    _server.listen((request) async {
      final path = request.uri.path;
      if (_requiresClientUserId(path) && !_hasClientUserId(request)) {
        _writeJson(request, <String, dynamic>{
          'code': 'INVALID_ARGUMENT',
          'message': 'X-Client-User-Id header required',
        }, statusCode: HttpStatus.badRequest);
        return;
      }
      if (path == '/content/feed') {
        _writeJson(request, {
          'items': _filteredFeed(request.uri.queryParameters),
          'outcome': 'content',
          'feedRequestId': 'fixture-feed-request-1',
          'objectCards': const <Map<String, Object?>>[],
        });
        return;
      }
      if (path.startsWith('/content/personas/') && path.endsWith('/posts')) {
        final userId = request.uri.pathSegments[2];
        final selectedIds = userId == 'fixture_user_current'
            ? _fixtures.userFeedSeed['myPostIds'] as List<dynamic>
            : _fixtures.userFeedSeed['authorPostIds'] as List<dynamic>;
        _writeJson(request, {
          'items': _contentPostsByIds(selectedIds),
          'hasMore': false,
        });
        return;
      }
      if (path == '/content/posts/fixture_photo_001') {
        _writeJson(request, _contentPostDetailWire('fixture_photo_001'));
        return;
      }
      if (path == '/chat/inbox') {
        _writeJson(request, {'items': _inboxRows()});
        return;
      }
      if (path == '/chat/conversations') {
        _writeJson(request, {'items': _inboxRows()});
        return;
      }
      if (path == '/chat/contacts') {
        _writeJson(request, {'items': _contactRows()});
        return;
      }
      if (path == '/chat/message-home') {
        _writeJson(request, {
          'items': _messageHomeRows(request.uri.queryParameters),
        });
        return;
      }
      if (path == '/chat/contact-home') {
        _writeJson(request, {
          'items': _contactHomeRows(request.uri.queryParameters),
        });
        return;
      }
      if (path.startsWith('/chat/conversations/') &&
          path.endsWith('/messages')) {
        // /chat/conversations/{conversationId}/messages
        final convId = path.split('/')[3];
        final messages =
            (_fixtures.chatSeed['messages'] as Map<String, dynamic>)[convId] ??
            const <dynamic>[];
        _writeJson(request, {'items': messages});
        return;
      }
      if (path.startsWith('/chat/conversations/') &&
          path.endsWith('/members')) {
        // /chat/conversations/{conversationId}/members
        final convId = path.split('/')[3];
        final members =
            (_fixtures.chatSeed['members'] as Map<String, dynamic>)[convId] ??
            const <dynamic>[];
        _writeJson(request, {'items': _memberRows(members as List<dynamic>)});
        return;
      }
      if (path == '/circles') {
        _writeJson(request, {'items': _circleRows()});
        return;
      }
      if (path == '/circles/fixture_circle_photo') {
        _writeJson(request, _circle('fixture_circle_photo'));
        return;
      }
      if (path.startsWith('/circles/') && path.endsWith('/feed')) {
        _writeJson(request, {
          'items': _contentPostsByIds(
            _fixtures.circleHomeSeed['groupFeedPostIds'] as List<dynamic>,
          ).map(contentPostWireFromReadModelMap).toList(growable: false),
        });
        return;
      }
      if (path == '/circles/fixture_circle_photo/groups') {
        final groups =
            (_fixtures.circleSeed['groups']
                as Map<String, dynamic>)['fixture_circle_photo'];
        _writeJson(request, {'items': groups});
        return;
      }
      if (path == '/user/profile') {
        _writeJson(request, {'items': _fixtures.userSeed['profiles']});
        return;
      }
      if (path == '/user/personas/active') {
        _writeJson(request, _activePersonaContext('fixture_user_current'));
        return;
      }
      if (path == '/me') {
        _writeJson(request, _profileWire(_profile('fixture_user_current')));
        return;
      }
      if (path == '/user/fixture_user_current') {
        _writeJson(request, _profileWire(_profile('fixture_user_current')));
        return;
      }
      if (path == '/users/fixture_user_current/works') {
        _writeJson(request, {
          'items': _contentPostsByIds(
            _fixtures.userFeedSeed['myPostIds'] as List<dynamic>,
          ).map(_workItem).toList(growable: false),
        });
        return;
      }
      if (path == '/users/fixture_user_photo/works') {
        _writeJson(request, {
          'items': _contentPostsByIds(
            _fixtures.userFeedSeed['authorPostIds'] as List<dynamic>,
          ).map(_workItem).toList(growable: false),
        });
        return;
      }
      if (path == '/users/fixture_user_current/life-items' ||
          path == '/users/fixture_user_photo/life-items') {
        _writeJson(request, {'items': <Map<String, dynamic>>[]});
        return;
      }
      if (path == '/users/fixture_user_current/circles' ||
          path == '/users/fixture_user_photo/circles') {
        _writeJson(request, {'items': _circleRows()});
        return;
      }
      if (path == '/homepages/search') {
        _writeJson(request, {'items': _fixtures.entitySeed['homepages']});
        return;
      }
      if (path == '/integration/external_integration/locations/pois') {
        _writeJson(request, {'items': _fixtures.integrationSeed['pois']});
        return;
      }
      if (path == '/app-messages') {
        _writeJson(request, {
          'items': _fixtures.notificationSeed['appMessages'],
          'unreadCount': _fixtures.notificationSeed['unreadCount'],
        });
        return;
      }
      if (path == '/rtc/calls') {
        _writeJson(request, {
          'items': _fixtures.rtcSeed['sessions'],
          'participants': _fixtures.rtcSeed['participants'],
        });
        return;
      }
      _writeJson(request, {
        'error': 'not found',
      }, statusCode: HttpStatus.notFound);
    });
  }

  Map<String, dynamic> _contentPost(String id) {
    return ((_fixtures.contentSeed['posts'] as List<dynamic>)
            .cast<Map<String, dynamic>>())
        .firstWhere((item) => item['postId'] == id);
  }

  List<Map<String, dynamic>> _filteredFeed(Map<String, String> query) {
    var items =
        ((_fixtures.contentSeed['posts'] as List<dynamic>)
                .cast<Map<String, dynamic>>())
            .toList(growable: false);
    final identity = query['identity'];
    final type = query['type'];
    final limit = int.tryParse(query['limit'] ?? '');
    if (identity != null && identity.isNotEmpty) {
      items = items
          .where((item) => item['contentIdentity'] == identity)
          .toList(growable: false);
    }
    if (type != null && type.isNotEmpty) {
      items = items
          .where((item) => item['contentType'] == type)
          .toList(growable: false);
    }
    if (limit != null) {
      items = items.take(limit).toList(growable: false);
    }
    return items.map(_contentFeedWire).toList(growable: false);
  }

  Map<String, dynamic> _contentFeedWire(Map<String, dynamic> source) =>
      Map<String, dynamic>.from(contentPostWireFromReadModelMap(source));

  /// canonical 场景种子同时承载服务内部存储键（objectKey / circleIds / themeTags
  /// 等），网关绝不会把它们透传给端侧。detail 响应因此只投影 Post 详情契约声明的
  /// 字段，让 fixture 与真实 wire 一样对未知字段 fail closed。
  Map<String, dynamic> _contentPostDetailWire(String id) {
    final source = _contentPost(id);
    final wire = _contentFeedWire(source);
    return <String, dynamic>{
      'postId': wire['postId'],
      'contentType': wire['contentType'],
      'status':
          source['status'] ??
          (source['publishedAt'] == null ? 'draft' : 'published'),
      'visibility': source['visibility'] ?? 'public',
      'likeCount': source['likeCount'] ?? 0,
      'commentCount': source['commentCount'] ?? 0,
      'shareCount': source['shareCount'] ?? 0,
      'viewCount': source['viewCount'] ?? 0,
      'createdAt': wire['createdAt'],
      'updatedAt': wire['updatedAt'],
      for (final field in const <String>[
        'contentIdentity',
        'assistantUsePolicy',
        'authorId',
        'authorDisplayName',
        'authorAvatarUrl',
        'title',
        'body',
        'summary',
        'mediaUrls',
        'coverUrl',
        'thumbnailUrl',
        'videoUrl',
        'width',
        'height',
        'durationMs',
        'contentVertical',
        'publishedAt',
      ])
        if (wire[field] != null) field: wire[field],
    };
  }

  List<Map<String, dynamic>> _contentPostsByIds(List<dynamic> ids) {
    final wanted = ids.map((id) => id.toString()).toSet();
    return ((_fixtures.contentSeed['posts'] as List<dynamic>)
            .cast<Map<String, dynamic>>())
        .where((item) => wanted.contains(item['postId']))
        .map(_contentFeedWire)
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _messageHomeRows(Map<String, String> query) {
    final filter = query['filter'] ?? 'all';
    if (filter == 'notification') {
      return const <Map<String, dynamic>>[];
    }
    final rows = _inboxRows()
        .where((item) {
          switch (filter) {
            case 'unread':
              return (item['unreadCount'] as num? ?? 0) > 0;
            case 'group':
              return item['type'] == 'group';
            case 'direct':
              return item['type'] == 'direct' || item['type'] == 'encrypted';
            default:
              return true;
          }
        })
        .map(
          (item) => <String, dynamic>{
            'id': item['id'],
            'kind': 'conversation',
            'conversationId': item['id'],
            'notificationId': '',
            'conversationType': item['type'],
            'title': item['title'],
            'summary': item['lastMessagePreview'],
            'avatarUrl': item['avatarUrl'],
            'groupAvatarVersion': item['groupAvatarVersion'] ?? 1,
            'lastActiveAt': item['lastMessageTime'],
            'unreadCount': item['unreadCount'] ?? 0,
            'mentionUnreadCount': item['mentionUnreadCount'] ?? 0,
            'muted': item['muted'] ?? false,
            'pinned': item['pinned'] ?? false,
            'notificationType': '',
            'read': (item['unreadCount'] as num? ?? 0) == 0,
          },
        )
        .toList(growable: false);
    final limit = int.tryParse(query['limit'] ?? '');
    if (limit != null && rows.length > limit) {
      return rows.take(limit).toList(growable: false);
    }
    return rows;
  }

  List<Map<String, dynamic>> _inboxRows() {
    final states = (_fixtures.chatSeed['userStates'] as List<dynamic>)
        .cast<Map<String, dynamic>>();
    final stateByConversationId = <String, Map<String, dynamic>>{
      for (final state in states) state['conversationId'].toString(): state,
    };
    return (_fixtures.chatSeed['conversations'] as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .map((conversation) {
          final id = conversation['id'].toString();
          final state = stateByConversationId[id] ?? const <String, dynamic>{};
          return <String, dynamic>{
            'id': id,
            'type': conversation['type'],
            'title': conversation['title'],
            'avatarUrl': conversation['avatarUrl'],
            'groupAvatarVersion': conversation['groupAvatarVersion'] ?? 0,
            'lastMessagePreview': conversation['lastMessagePreview'],
            'lastMessageType': 'text',
            'lastMessageTime': conversation['lastMessageTime'],
            'lastSeq': conversation['maxSeq'] ?? 0,
            'unreadCount': state['unreadCount'] ?? 0,
            'mentionUnreadCount': state['mentionUnreadCount'] ?? 0,
            'muted': state['muted'] ?? false,
            'pinned': state['pinned'] ?? false,
            'circleId': conversation['circleId'] ?? '',
          };
        })
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _contactHomeRows(Map<String, String> query) {
    final filter = query['filter'] ?? 'all';
    final rows = <Map<String, dynamic>>[];
    if (filter == 'all' || filter == 'mutual') {
      for (final contact
          in (_fixtures.chatContactsSeed['contacts'] as List<dynamic>)
              .cast<Map<String, dynamic>>()) {
        if (filter == 'mutual' && contact['relationState'] != 'mutual') {
          continue;
        }
        rows.add(<String, dynamic>{
          'id': contact['userId'],
          'kind': 'user',
          'objectId': contact['userId'],
          'userId': contact['userId'],
          'userHandle': contact['userHandle'],
          'title': contact['displayName'],
          'subtitle': contact['bio'],
          'avatarUrl': contact['avatarUrl'],
          'relationState': contact['relationState'],
        });
      }
    }
    if (filter == 'all' || filter == 'circle') {
      for (final circle
          in (_fixtures.circleSeed['circles'] as List<dynamic>)
              .cast<Map<String, dynamic>>()) {
        rows.add(<String, dynamic>{
          'id': circle['id'],
          'kind': 'circle',
          'objectId': circle['id'],
          'userHandle': '',
          'circleId': circle['id'],
          'title': circle['name'],
          'subtitle': circle['description'],
          'avatarUrl': circle['avatarUrl'],
        });
      }
    }
    if (filter == 'all' || filter == 'group') {
      final membersByConversation =
          _fixtures.chatSeed['members'] as Map<String, dynamic>;
      for (final conversation in _inboxRows()) {
        if (conversation['type'] != 'group') {
          continue;
        }
        final conversationId = conversation['id'].toString();
        final members =
            membersByConversation[conversationId] as List? ?? const <dynamic>[];
        rows.add(<String, dynamic>{
          'id': conversationId,
          'kind': 'group',
          'objectId': conversationId,
          'userHandle': '',
          'conversationId': conversationId,
          'circleId': conversation['circleId'] ?? '',
          'title': conversation['title'],
          'subtitle': conversation['lastMessagePreview'],
          'avatarUrl': conversation['avatarUrl'],
          'memberCount': members.length,
          'lastActiveAt': conversation['lastMessageTime'],
        });
      }
    }
    final normalized = rows
        .map(
          (row) => <String, dynamic>{
            ...row,
            'subtitle': row['subtitle'] ?? '',
            'avatarUrl': row['avatarUrl'] ?? '',
            'summaryIntersections':
                row['summaryIntersections'] ?? const <String>[],
            'contactCount': row['contactCount'] ?? 0,
            'sortKey': row['sortKey'] ?? row['id'],
          },
        )
        .toList();
    final limit = int.tryParse(query['limit'] ?? '');
    if (limit != null && normalized.length > limit) {
      return normalized.take(limit).toList(growable: false);
    }
    return normalized;
  }

  List<Map<String, dynamic>> _contactRows() {
    return (_fixtures.chatContactsSeed['contacts'] as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .map(
          (contact) => <String, dynamic>{
            'userId': contact['userId'],
            'userHandle': contact['userHandle'],
            'displayName': contact['displayName'] ?? '',
            'avatarUrl': contact['avatarUrl'] ?? '',
            'bio': contact['bio'] ?? '',
            'metFrom': contact['metFrom'] ?? '',
            'lastInteraction': contact['lastInteraction'] ?? '',
            'relationState': contact['relationState'] ?? 'not_following',
            'conversationId': contact['conversationId'] ?? '',
            'conversationType': contact['conversationType'] ?? 'direct',
            'subtitle': contact['subtitle'] ?? '',
            'highlightText': contact['highlightText'] ?? '',
            'matchedField': contact['matchedField'] ?? '',
            'source': contact['source'] ?? '',
            'isStarred': contact['isStarred'] ?? false,
          },
        )
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _memberRows(List<dynamic> members) {
    return members
        .cast<Map<String, dynamic>>()
        .map(
          (member) => <String, dynamic>{
            'userId': member['userId'],
            'userHandle': member['userHandle'],
            'displayName': member['displayName'] ?? '',
            'avatarUrl': member['avatarUrl'] ?? '',
            'role': member['role'] ?? 'member',
            'memberType': member['memberType'] ?? 'user',
            'joinedAt': member['joinedAt'],
            'isCurrentUser': member['isCurrentUser'] ?? false,
          },
        )
        .toList(growable: false);
  }

  Map<String, dynamic> _circle(String id) {
    final row =
        ((_fixtures.circleSeed['circles'] as List<dynamic>)
                .cast<Map<String, dynamic>>())
            .firstWhere((item) => item['id'] == id);
    return _circleWire(row);
  }

  List<Map<String, dynamic>> _circleRows() {
    return ((_fixtures.circleSeed['circles'] as List<dynamic>)
            .cast<Map<String, dynamic>>())
        .map(_circleWire)
        .toList(growable: false);
  }

  /// Circle 契约不再承载 viewer 作用域字段（role / joinStatus / isFollowed）与服务
  /// 内部存储键；它们分别由 CircleMembership 与媒体授权链路提供，网关不会透传。
  Map<String, dynamic> _circleWire(Map<String, dynamic> row) {
    return <String, dynamic>{
      'id': row['id'],
      'name': row['name'],
      'description': row['description'],
      'coverUrl': row['coverUrl'],
      'ownerId': row['ownerId'],
      'ownerDisplayNameSnapshot': row['ownerDisplayNameSnapshot'],
      'category': row['category'] ?? row['categoryId'],
      'subCategory': row['subCategory'],
      'tags': row['tags'] ?? const <String>[],
      'memberCount': row['memberCount'] ?? 0,
      'postCount': row['postCount'] ?? 0,
      'weeklyActiveCount': row['weeklyActiveCount'] ?? 0,
      'version': row['version'] ?? 1,
      'status': row['status'] ?? 'active',
      'visibility': row['visibility'],
      'joinPolicy': row['joinPolicy'],
      'kind': row['kind'] ?? 'interest',
      'displaySubjectType': row['displaySubjectType'] ?? 'circle',
      'followEnabled': row['followEnabled'] ?? true,
      'defaultPublicGroupId': row['defaultPublicGroupId'],
      'autoSyncChat': row['autoSyncChat'] ?? false,
      'storageUsedBytes': row['storageUsedBytes'] ?? 0,
      'storageQuotaBytes': row['storageQuotaBytes'] ?? 1073741824,
      'domainId': row['domainId'],
      'createdAt': row['createdAt'],
      'updatedAt': row['updatedAt'],
    };
  }

  Map<String, dynamic> _profile(String id) {
    return ((_fixtures.userSeed['profiles'] as List<dynamic>)
            .cast<Map<String, dynamic>>())
        .firstWhere((item) => item['userId'] == id);
  }

  Map<String, dynamic> _profileWire(Map<String, dynamic> profile) {
    final stats = (profile['stats'] as Map<String, dynamic>?) ?? {};
    final userId = profile['userId'].toString();
    return <String, dynamic>{
      'personaId': userId,
      'userHandle': userId,
      'displayName': profile['displayName'],
      'nicknameCustomized': profile['nicknameCustomized'] ?? false,
      'subjectType': 'account',
      'avatarUrl': profile['avatarUrl'],
      'backgroundUrl': profile['backgroundUrl'],
      'bio': profile['bio'],
      'followingCount': stats['followingCount'] ?? 0,
      'followerCount': stats['followerCount'] ?? 0,
      'postCount': stats['postCount'] ?? 0,
      'circleCount': stats['circleCount'] ?? 0,
      'likeCount': stats['likeCount'] ?? 0,
      'profileVisibility': profile['profileVisibility'] ?? 'public',
      'isolationLevel': profile['isolationLevel'] ?? 'open',
      'inheritsFromOwner': profile['inheritsFromOwner'] ?? true,
      'updatedAt': profile['updatedAt'] ?? '2026-07-20T00:00:00Z',
    };
  }

  Map<String, dynamic> _activePersonaContext(String userId) {
    final profile = _profile(userId);
    return <String, dynamic>{
      'ownerUserId': userId,
      'personaId': userId,
      'subjectType': 'account',
      'displayName': profile['displayName'],
      'avatarUrl': profile['avatarUrl'],
      'avatarVersion': profile['avatarVersion'] ?? 1,
      'isPrimary': true,
      'isolationLevel': profile['isolationLevel'] ?? 'open',
      'profileVisibility': profile['profileVisibility'] ?? 'public',
      'contextVersion': 1,
      'personaSnapshotVersion': 1,
      'explicitOverride': false,
      'switchedAt': '2026-07-20T00:00:00Z',
    };
  }

  Map<String, dynamic> _workItem(Map<String, dynamic> post) {
    return <String, dynamic>{
      'id': post['postId'],
      'type': post['contentType'],
      'title': post['title'] ?? '',
      'coverUrl': post['coverUrl'] ?? '',
      'likeCount': post['likeCount'] ?? 0,
      'date': post['createdAt'] ?? '',
      'desc': post['summary'] ?? '',
    };
  }

  void _writeJson(
    HttpRequest request,
    Object payload, {
    int statusCode = HttpStatus.ok,
  }) {
    request.response
      ..statusCode = statusCode
      ..headers.contentType = ContentType.json
      ..write(json.encode(payload));
    request.response.close();
  }

  bool _requiresClientUserId(String path) {
    return path.startsWith('/chat');
  }

  bool _hasClientUserId(HttpRequest request) {
    final userId = request.headers.value('X-Client-User-Id')?.trim() ?? '';
    final personaId =
        request.headers.value('X-Client-Persona-Id')?.trim() ?? '';
    return userId.isNotEmpty || personaId.isNotEmpty;
  }
}

final class _BusinessFixtureAuthTokenProvider
    implements CloudAuthTokenProvider {
  const _BusinessFixtureAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'business-fixture-token';
}

final class _BusinessFixtureClientContext
    implements CloudClientContextProvider {
  const _BusinessFixtureClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'business-fixture-session',
      deviceActorId: 'business-fixture-device',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _NoopCloudOperationTelemetrySink
    implements CloudOperationTelemetrySink {
  const _NoopCloudOperationTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
