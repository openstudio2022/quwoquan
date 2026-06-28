import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/recommendation/intersection_action_keys.dart';
import 'package:quwoquan_app/cloud/services/connection/connection_models.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 同频/广场社交连接 Repository（三层模式：Abstract → Mock → Remote）。
///
/// 承载「同趣 / 同行 / 附近 / 局」四条连接通道。原型阶段：
///   - Mock：行内 canonical 强类型数据（复用四川目的地实体 id），不发 HTTP。
///   - Remote：后端契约（service.yaml / fields.yaml / errors.yaml）尚未上线，
///     方法返回结构化 [RuntimeFailure] unavailable，**不整类委托 Mock**（守 R16）。
///
/// 后端 aggregate / Go 实现 / migration / 附近 LBS / 双向同意风控登记 backlog。
abstract class ConnectionRepository {
  /// 同频连接中心四 tab 计数摘要。
  Future<ConnectionHubSummary> getHubSummary();

  /// 同趣的人（基于共同兴趣推荐，无地理位置）。
  Future<List<PeerConnection>> listAffinityPeers({int limit});

  /// 附近同趣的人（带模糊位置，需定位授权；含双向同意/隐私收敛态）。
  Future<List<PeerConnection>> listNearbyPeers({int limit});

  /// 结伴 / 行程机会（围绕目的地实体）。
  Future<List<CompanionTrip>> listCompanionTrips({int limit});

  /// 线下局（可报名的同城聚会）。
  Future<List<OfflineMeetup>> listOfflineMeetups({int limit});
}

/// Mock 实现：本地 canonical 连接数据，不发 HTTP。
///
/// Canonical 数据与 `contracts/metadata/_shared/test_fixtures/connection_plaza_seed.yaml`
/// 对齐（原型阶段行内维护；方向确认后改为 ContractFixtureRuntimeLoader 加载）。
/// actionKey 取 [IntersectionActionKeys] 闭集，文案统一经
/// [DiscoveryFeedText.intersectionActionLabel]，端不二次造表（守 R06）。
class MockConnectionRepository implements ConnectionRepository {
  const MockConnectionRepository();

  static ConnectionActionHint _action(String key, {bool primary = true}) {
    return ConnectionActionHint(
      actionKey: key,
      label: DiscoveryFeedText.intersectionActionLabel(key),
      isPrimary: primary,
    );
  }

  @override
  Future<ConnectionHubSummary> getHubSummary() async {
    return ConnectionHubSummary(
      affinityCount: _affinityPeers().length,
      companionCount: _companionTrips().length,
      nearbyCount: _nearbyPeers().length,
      meetupCount: _offlineMeetups().length,
    );
  }

  @override
  Future<List<PeerConnection>> listAffinityPeers({int limit = 20}) async {
    final items = _affinityPeers();
    return items.length <= limit ? items : items.sublist(0, limit);
  }

  @override
  Future<List<PeerConnection>> listNearbyPeers({int limit = 20}) async {
    final items = _nearbyPeers();
    return items.length <= limit ? items : items.sublist(0, limit);
  }

  @override
  Future<List<CompanionTrip>> listCompanionTrips({int limit = 20}) async {
    final items = _companionTrips();
    return items.length <= limit ? items : items.sublist(0, limit);
  }

  @override
  Future<List<OfflineMeetup>> listOfflineMeetups({int limit = 20}) async {
    final items = _offlineMeetups();
    return items.length <= limit ? items : items.sublist(0, limit);
  }

  static List<PeerConnection> _affinityPeers() {
    return <PeerConnection>[
      PeerConnection(
        id: 'peer_affinity_aman',
        displayName: '阿曼的山野',
        avatarUrl: '',
        headline: '徒步｜露营｜川西自驾',
        sharedSummary: '你们都收藏了稻城亚丁，且都喜欢徒步与露营',
        sharedInterests: const <String>['徒步', '露营', '川西自驾'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.joinTopicRoom),
          _action(IntersectionActionKeys.expressInterest, primary: false),
        ],
        activeStatusLabel: '今天活跃',
      ),
      PeerConnection(
        id: 'peer_affinity_lin',
        displayName: '林深见鹿',
        avatarUrl: '',
        headline: '风光摄影｜A7M4｜追逐光影',
        sharedSummary: '你们都在看「稻城亚丁线」，关注同 3 个摄影话题',
        sharedInterests: const <String>['风光摄影', '后期调色', '观星'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.joinTopicRoom),
          _action(IntersectionActionKeys.expressInterest, primary: false),
        ],
        activeStatusLabel: '2 小时前活跃',
      ),
      PeerConnection(
        id: 'peer_affinity_zhou',
        displayName: '周末不在家',
        avatarUrl: '',
        headline: '骑行｜城市漫步｜咖啡',
        sharedSummary: '你们都加入了「川西自驾圈」，都喜欢骑行',
        sharedInterests: const <String>['骑行', '城市漫步', '精品咖啡'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.expressInterest),
        ],
        activeStatusLabel: '昨天活跃',
      ),
    ];
  }

  static List<PeerConnection> _nearbyPeers() {
    return <PeerConnection>[
      PeerConnection(
        id: 'peer_nearby_chuan',
        displayName: '川西风很大',
        avatarUrl: '',
        headline: '想找搭子周末去毕棚沟',
        sharedSummary: '你们都想去毕棚沟，都喜欢徒步',
        sharedInterests: const <String>['徒步', '自驾'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.meetNearby),
        ],
        distanceLabel: '约 1.2km',
        activeStatusLabel: '刚刚活跃',
      ),
      PeerConnection(
        id: 'peer_nearby_photo',
        displayName: '街角胶片',
        avatarUrl: '',
        headline: '同城扫街｜想约拍',
        sharedSummary: '你们都关注「街拍」，都在附近常出没',
        sharedInterests: const <String>['街拍', '胶片'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.meetNearby),
        ],
        distanceLabel: '约 800m',
        activeStatusLabel: '30 分钟前活跃',
      ),
      PeerConnection(
        id: 'peer_nearby_anon',
        displayName: '一位同频的人',
        avatarUrl: '',
        headline: '附近｜资料已隐藏',
        sharedSummary: '你们有 2 个共同兴趣，对方资料默认收敛',
        sharedInterests: const <String>['美食', '露营'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.meetNearby),
        ],
        distanceLabel: '约 2km',
        mutualConsentRequired: true,
        privacyBlurred: true,
      ),
    ];
  }

  static List<CompanionTrip> _companionTrips() {
    return <CompanionTrip>[
      CompanionTrip(
        id: 'trip_daocheng_weekend',
        destinationName: '稻城亚丁',
        destinationEntityId: 'fixture_homepage_travel_route_daocheng',
        coverImageUrl: '',
        dateRangeLabel: '下周五–周日',
        companionSummary: '5 人下周也去稻城亚丁',
        organizerName: '高原的风',
        organizerAvatarUrl: '',
        companionAvatars: const <String>['', '', '', ''],
        tags: const <String>['3 天 2 晚', '拼车', '摄影'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.joinTrip),
          _action(IntersectionActionKeys.startCompanion, primary: false),
        ],
      ),
      CompanionTrip(
        id: 'trip_chuanxi_loop',
        destinationName: '川西小环线',
        destinationEntityId: 'fixture_homepage_travel_route_chuanxi',
        coverImageUrl: '',
        dateRangeLabel: '本月底',
        companionSummary: '3 人正在凑川西小环线的车',
        organizerName: '甘孜在路上',
        organizerAvatarUrl: '',
        companionAvatars: const <String>['', ''],
        tags: const <String>['7 天', '自驾', 'AA 制'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.joinTrip),
          _action(IntersectionActionKeys.startCompanion, primary: false),
        ],
      ),
      CompanionTrip(
        id: 'trip_emeishan_sunrise',
        destinationName: '峨眉山',
        destinationEntityId: 'homepage_sight_emeishan',
        coverImageUrl: '',
        dateRangeLabel: '下个周末',
        companionSummary: '2 人想一起爬峨眉看日出',
        organizerName: '云海收集者',
        organizerAvatarUrl: '',
        companionAvatars: const <String>[''],
        tags: const <String>['2 天 1 晚', '登山', '日出'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.startCompanion),
        ],
      ),
    ];
  }

  static List<OfflineMeetup> _offlineMeetups() {
    return <OfflineMeetup>[
      OfflineMeetup(
        id: 'meetup_cd_photo_walk',
        title: '成都·夜市扫街局',
        placeName: '建设路夜市',
        timeLabel: '周六 18:30',
        attendanceLabel: '3/8 人已报名',
        hostName: '快门青年',
        hostAvatarUrl: '',
        coverImageUrl: '',
        tags: const <String>['摄影', '美食', '同城'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.joinMeetup),
        ],
      ),
      OfflineMeetup(
        id: 'meetup_cd_boardgame',
        title: '周日下午·桌游局',
        placeName: '春熙路桌游馆',
        timeLabel: '周日 14:00',
        attendanceLabel: '5/6 人已报名',
        hostName: '狼人局局长',
        hostAvatarUrl: '',
        coverImageUrl: '',
        tags: const <String>['桌游', '社交', '室内'],
        actions: <ConnectionActionHint>[
          _action(IntersectionActionKeys.joinMeetup),
        ],
      ),
    ];
  }
}

/// Remote 实现：connection 后端尚未上线，方法返回结构化 unavailable 失败。
///
/// 不整类委托 Mock（守 R16）；待后端契约落地后逐方法替换为真实 HTTP 调用。
class RemoteConnectionRepository implements ConnectionRepository {
  const RemoteConnectionRepository();

  static const String _unavailableCode = 'APP.UNAVAILABLE.not_implemented';

  Never _unavailable(String method) {
    final failure = RuntimeFailure(
      code: _unavailableCode,
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.internal,
      nature: RuntimeFailureNature.bug,
      location: const RuntimeFailureLocation(
        businessObject: 'connection',
        functionModule: 'connection_repository_remote',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'method', value: method),
          RuntimeContextAttribute(key: 'status', value: 'deferred'),
        ],
      ),
    );
    throw CloudException(
      type: CloudErrorType.server,
      message: 'connection remote not implemented: $method',
      code: failure.code,
      runtimeFailure: failure,
    );
  }

  @override
  Future<ConnectionHubSummary> getHubSummary() async => _unavailable('getHubSummary');

  @override
  Future<List<PeerConnection>> listAffinityPeers({int limit = 20}) async =>
      _unavailable('listAffinityPeers');

  @override
  Future<List<PeerConnection>> listNearbyPeers({int limit = 20}) async =>
      _unavailable('listNearbyPeers');

  @override
  Future<List<CompanionTrip>> listCompanionTrips({int limit = 20}) async =>
      _unavailable('listCompanionTrips');

  @override
  Future<List<OfflineMeetup>> listOfflineMeetups({int limit = 20}) async =>
      _unavailable('listOfflineMeetups');
}
