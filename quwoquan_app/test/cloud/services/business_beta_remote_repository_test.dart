import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/chat/remote/chat_repository_remote.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';

void main() {
  test(
    'beta RemoteRepository reads contract fixture data through HTTP',
    () async {
      final fixtures = _BusinessFixtures.load();
      final server = await _ContractSeedHttpServer.start(fixtures);
      addTearDown(server.close);

      final baseUrl = 'http://${server.address.host}:${server.port}';
      final contentRepository = RemoteContentRepository(baseUrl: baseUrl);
      final chatRepository = RemoteChatRepository(baseUrl: baseUrl);
      final circleRepository = RemoteCircleRepository(baseUrl: baseUrl);
      final userRepository = RemoteUserProfileRepository(baseUrl: baseUrl);

      final photoFeed = await contentRepository.listDiscoveryFeed(
        category: 'photo',
        identity: 'work',
        type: 'photo',
        limit: 20,
      );
      expect(photoFeed.length, greaterThanOrEqualTo(3));
      expect(photoFeed.map((item) => item.id), contains('fixture_photo_001'));
      expect(
        photoFeed.every((item) => item.primaryVisualUrl.startsWith('https://')),
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
      final post = await contentRepository.getPost(postId: 'fixture_photo_001');
      expect(post.post.id, 'fixture_photo_001');

      final inbox = await chatRepository.listInbox(limit: 20);
      expect(inbox.length, greaterThanOrEqualTo(5));
      expect(inbox.map((item) => item.id), contains('fixture_conv_direct'));
      expect(
        inbox.every((item) => item.avatarUrl.trim().isNotEmpty),
        isTrue,
      );
      final messages = await chatRepository.listMessages(
        conversationId: 'fixture_conv_direct',
        limit: 20,
      );
      expect(messages.map((item) => item.id), contains('fixture_msg_direct_1'));
      final contacts = await chatRepository.listContacts(limit: 20);
      expect(contacts.length, greaterThanOrEqualTo(6));
      expect(
        contacts.map((item) => item.userId),
        contains('fixture_user_friend'),
      );
      final groupMembers = await chatRepository.listMembers(
        conversationId: 'fixture_conv_group',
        limit: 20,
      );
      final contactIds = contacts.map((item) => item.userId).toSet();
      expect(
        groupMembers
            .where((member) => !member.isCurrentUser)
            .every((member) => contactIds.contains(member.userId)),
        isTrue,
      );
      final contactCircles = await chatRepository.listContactTabCircles(
        limit: 20,
      );
      expect(
        contactCircles.map((item) => item.circleId),
        contains('fixture_circle_photo'),
      );
      final funGroups = await chatRepository.listContactTabFunGroups(limit: 20);
      expect(
        funGroups.map((item) => item.conversationId),
        contains('fixture_conv_group'),
      );

      final circles = await circleRepository.listCircles(limit: 20);
      expect(circles.length, greaterThanOrEqualTo(6));
      expect(circles.map((item) => item.id), contains('fixture_circle_photo'));
      expect(
        circles.every((item) => item.coverUrl?.startsWith('https://') == true),
        isTrue,
      );
      final circle = await circleRepository.getCircle('fixture_circle_photo');
      expect(circle.circle.id, 'fixture_circle_photo');
      final groups = await circleRepository.listCircleGroups(
        'fixture_circle_photo',
        limit: 20,
      );
      expect(
        groups.map((item) => item.id),
        contains('fixture_group_photo_public'),
      );
      final circleHomeFeed = await circleRepository.listHomeCircleDiscoveryFeed(
        limit: 20,
      );
      expect(
        circleHomeFeed.map((item) => item.id),
        contains('fixture_photo_001'),
      );
      expect(circleHomeFeed.length, greaterThanOrEqualTo(5));
      expect(
        circleHomeFeed.every(
          (item) => item.primaryVisualUrl.startsWith('https://'),
        ),
        isTrue,
      );

      final currentUser = await userRepository.getUserProfile(
        'fixture_user_current',
      );
      expect(currentUser.displayName, '契约当前用户');
      expect(currentUser.backgroundUrl.startsWith('https://'), isTrue);
      final userPosts = await userRepository.listUserPosts(
        'fixture_user_current',
        limit: 20,
      );
      expect(userPosts.length, greaterThanOrEqualTo(4));
      expect(userPosts.map((item) => item.id), contains('fixture_moment_001'));
      expect(
        userPosts.every((item) => item.primaryVisualUrl.startsWith('https://')),
        isTrue,
      );
      final userWorks = await userRepository.listUserWorks(
        'fixture_user_photo',
      );
      expect(userWorks.map((item) => item.id), contains('fixture_photo_001'));
      final userCircles = await userRepository.listUserCircles(
        'fixture_user_current',
        limit: 20,
      );
      expect(
        userCircles.map((item) => item.id),
        contains('fixture_circle_photo'),
      );

      final userProfiles = await _getJsonList(
        '$baseUrl/v1/user/profile',
        'items',
      );
      expect(
        userProfiles.map((item) => item['userId']),
        contains('fixture_user_current'),
      );

      final homepages = await _getJsonList(
        '$baseUrl/v1/entity/homepages',
        'items',
      );
      expect(
        homepages.map((item) => item['homepageId']),
        contains('fixture_homepage_author'),
      );

      final pois = await _getJsonList(
        '$baseUrl/v1/integration/locations/pois',
        'items',
      );
      expect(
        pois.map((item) => item['poiId']),
        contains('fixture_poi_west_lake'),
      );

      final appMessages = await _getJsonList(
        '$baseUrl/v1/app-messages',
        'items',
      );
      expect(
        appMessages.map((item) => item['messageId']),
        contains('fixture_app_message_assistant_stock'),
      );

      final calls = await _getJsonList('$baseUrl/v1/rtc/calls', 'items');
      expect(
        calls.map((item) => item['sessionId']),
        contains('fixture_call_voice'),
      );
    },
  );
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
      '../quwoquan_service/contracts/metadata/content/test_fixtures/scenarios/content_scenarios.json',
    );
    final chat = _loadFixture(
      '../quwoquan_service/contracts/metadata/messages/chat/test_fixtures/scenarios/chat_scenarios.json',
    );
    final circle = _loadFixture(
      '../quwoquan_service/contracts/metadata/social/circle/test_fixtures/scenarios/circle_scenarios.json',
    );
    final user = _loadFixture(
      '../quwoquan_service/contracts/metadata/user/test_fixtures/scenarios/user_scenarios.json',
    );
    final entity = _loadFixture(
      '../quwoquan_service/contracts/metadata/entity/test_fixtures/scenarios/entity_scenarios.json',
    );
    final integration = _loadFixture(
      '../quwoquan_service/contracts/metadata/integration/test_fixtures/scenarios/integration_scenarios.json',
    );
    final notification = _loadFixture(
      '../quwoquan_service/contracts/metadata/notification/test_fixtures/scenarios/notification_scenarios.json',
    );
    final rtc = _loadFixture(
      '../quwoquan_service/contracts/metadata/rtc/test_fixtures/scenarios/rtc_scenarios.json',
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
      if (path == '/v1/content/feed') {
        _writeJson(request, {
          'items': _filteredFeed(request.uri.queryParameters),
        });
        return;
      }
      if (path.startsWith('/v1/content/profile-subjects/') &&
          path.endsWith('/posts')) {
        final userId = path.split('/')[4];
        final selectedIds = userId == 'fixture_user_current'
            ? _fixtures.userFeedSeed['myPostIds'] as List<dynamic>
            : _fixtures.userFeedSeed['authorPostIds'] as List<dynamic>;
        _writeJson(request, {'items': _contentPostsByIds(selectedIds)});
        return;
      }
      if (path == '/v1/content/posts/fixture_photo_001') {
        _writeJson(request, _contentPost('fixture_photo_001'));
        return;
      }
      if (path == '/v1/chat/inbox') {
        _writeJson(request, {'items': _fixtures.chatSeed['conversations']});
        return;
      }
      if (path == '/v1/chat/conversations') {
        _writeJson(request, {'items': _fixtures.chatSeed['conversations']});
        return;
      }
      if (path == '/v1/chat/contacts') {
        _writeJson(request, {'items': _fixtures.chatContactsSeed['contacts']});
        return;
      }
      if (path.startsWith('/v1/chat/conversations/') &&
          path.endsWith('/messages')) {
        final convId = path.split('/')[4];
        final messages =
            (_fixtures.chatSeed['messages'] as Map<String, dynamic>)[convId];
        _writeJson(request, {'items': messages});
        return;
      }
      if (path.startsWith('/v1/chat/conversations/') &&
          path.endsWith('/members')) {
        final convId = path.split('/')[4];
        final members =
            (_fixtures.chatSeed['members'] as Map<String, dynamic>)[convId];
        _writeJson(request, {'items': members});
        return;
      }
      if (path == '/v1/circles') {
        _writeJson(request, {'items': _fixtures.circleSeed['circles']});
        return;
      }
      if (path == '/v1/circles/fixture_circle_photo') {
        _writeJson(request, {'data': _circle('fixture_circle_photo')});
        return;
      }
      if (path.startsWith('/v1/circles/') && path.endsWith('/feed')) {
        _writeJson(request, {
          'items': _contentPostsByIds(
            _fixtures.circleHomeSeed['groupFeedPostIds'] as List<dynamic>,
          ),
        });
        return;
      }
      if (path == '/v1/circles/fixture_circle_photo/groups') {
        final groups =
            (_fixtures.circleSeed['groups']
                as Map<String, dynamic>)['fixture_circle_photo'];
        _writeJson(request, {'items': groups});
        return;
      }
      if (path == '/v1/user/profile') {
        _writeJson(request, {'items': _fixtures.userSeed['profiles']});
        return;
      }
      if (path == '/v1/me') {
        _writeJson(request, _profileWire(_profile('fixture_user_current')));
        return;
      }
      if (path == '/v1/user/fixture_user_current') {
        _writeJson(request, _profileWire(_profile('fixture_user_current')));
        return;
      }
      if (path == '/v1/users/fixture_user_current/works') {
        _writeJson(request, {
          'items': _contentPostsByIds(
            _fixtures.userFeedSeed['myPostIds'] as List<dynamic>,
          ).map(_workItem).toList(growable: false),
        });
        return;
      }
      if (path == '/v1/users/fixture_user_photo/works') {
        _writeJson(request, {
          'items': _contentPostsByIds(
            _fixtures.userFeedSeed['authorPostIds'] as List<dynamic>,
          ).map(_workItem).toList(growable: false),
        });
        return;
      }
      if (path == '/v1/users/fixture_user_current/life-items' ||
          path == '/v1/users/fixture_user_photo/life-items') {
        _writeJson(request, {'items': <Map<String, dynamic>>[]});
        return;
      }
      if (path == '/v1/users/fixture_user_current/circles' ||
          path == '/v1/users/fixture_user_photo/circles') {
        _writeJson(request, {'items': _fixtures.circleSeed['circles']});
        return;
      }
      if (path == '/v1/entity/homepages') {
        _writeJson(request, {'items': _fixtures.entitySeed['homepages']});
        return;
      }
      if (path == '/v1/integration/locations/pois') {
        _writeJson(request, {'items': _fixtures.integrationSeed['pois']});
        return;
      }
      if (path == '/v1/app-messages') {
        _writeJson(request, {
          'items': _fixtures.notificationSeed['appMessages'],
          'unreadCount': _fixtures.notificationSeed['unreadCount'],
        });
        return;
      }
      if (path == '/v1/rtc/calls') {
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
        .firstWhere((item) => item['id'] == id || item['postId'] == id);
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
          .where(
            (item) => (item['identity'] ?? item['contentIdentity']) == identity,
          )
          .toList(growable: false);
    }
    if (type != null && type.isNotEmpty) {
      items = items
          .where((item) => (item['type'] ?? item['contentType']) == type)
          .toList(growable: false);
    }
    if (limit != null) {
      items = items.take(limit).toList(growable: false);
    }
    return items;
  }

  List<Map<String, dynamic>> _contentPostsByIds(List<dynamic> ids) {
    final wanted = ids.map((id) => id.toString()).toSet();
    return ((_fixtures.contentSeed['posts'] as List<dynamic>)
            .cast<Map<String, dynamic>>())
        .where((item) => wanted.contains(item['id'] ?? item['postId']))
        .toList(growable: false);
  }

  Map<String, dynamic> _circle(String id) {
    return ((_fixtures.circleSeed['circles'] as List<dynamic>)
            .cast<Map<String, dynamic>>())
        .firstWhere((item) => item['id'] == id || item['_id'] == id);
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
      'profileSubjectId': userId,
      'ownerUserId': userId,
      'userHandle': userId,
      'username': userId,
      'nickname': profile['displayName'],
      'displayName': profile['displayName'],
      'subjectType': 'user',
      'avatarUrl': profile['avatarUrl'],
      'backgroundUrl': profile['backgroundUrl'],
      'bio': profile['bio'],
      'followingCount': stats['followingCount'] ?? 0,
      'followerCount': stats['followerCount'] ?? 0,
      'postCount': stats['postCount'] ?? 0,
      'circleCount': stats['circleCount'] ?? 0,
      'likeCount': stats['likeCount'] ?? 0,
    };
  }

  Map<String, dynamic> _workItem(Map<String, dynamic> post) {
    return <String, dynamic>{
      'id': post['id'] ?? post['postId'],
      'type': post['type'] ?? post['contentType'],
      'title': post['title'] ?? post['body'] ?? post['summary'],
      'coverUrl': post['coverUrl'] ?? post['thumbnailUrl'],
      'likeCount': post['likeCount'] ?? 0,
      'date': post['createdAt'] ?? post['publishedAt'] ?? '',
      'desc': post['summary'] ?? post['body'] ?? '',
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
}
