import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/core/platform/location/location_gateway.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/cloud/services/user/profile_media_upload_gateway.dart';
import 'package:quwoquan_app/cloud/services/user/contact_discovery_repository.dart';
import 'package:quwoquan_app/cloud/services/user/following_subject_repository.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/remote/content/media/local_media_upload_source.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/mock/homepage_repository_mock.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import 'package:quwoquan_app/core/services/remote_search_repository.dart';
import 'package:quwoquan_app/infrastructure/local/content/filter_catalog/verified_filter_catalog_store.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

import 'alpha_chat_repository.dart';
import 'alpha_circle_query_reader.dart';
import 'alpha_content_adapters.dart';
import 'alpha_intersection_repository.dart';
import 'alpha_realtime_connection_delegate.dart';
import 'alpha_user_profile_repository.dart' hide ContractFixtureRuntimeLoader;
import 'alpha_user_repository.dart';

/// Alpha-only dependency composition. Production never imports this runner.
List<Override> buildAlphaCloudOverrides() {
  final locationQuery = AlphaLocationQueryAdapter();
  final reportWriter = AlphaContentReportAdapter();
  final contentFixture = AlphaContentRepository();
  final filterCatalog = AlphaFilterCatalogQuery();
  final footprintFixture = AlphaFootprintRepository();
  final homepages = MockHomepageRepository();
  final homepageReviews = AlphaHomepageReviewFacet();
  final personaRelationships = AlphaPersonaRelationshipFacet();
  final subjectFollows = AlphaSubjectFollowFacet();
  final comments = AlphaContentCommentFacet();
  final circles = MockCircleRepository();
  final circlePlacementStore = AlphaCirclePostPlacementStore();
  final circleQueries = AlphaCircleQueryReader(circles, circlePlacementStore);
  final postReactions = AlphaContentPostReactionFacet();
  final postPublication = AlphaContentPostPublicationWriter();
  final appMessages = AlphaAppMessageAdapter();
  final chatState = AlphaChatStateEngine();
  final chatRepository = MockChatRepository(engine: chatState);
  final chatMessages = AlphaChatMessageCommandWriter(engine: chatState);
  final media = AlphaContentMediaFacet();
  final outboundShares = AlphaContentOutboundShareWriter();
  final profileInteractions = AlphaProfileInteractionFacet();
  final circlePostPlacements = AlphaCirclePostPlacementWriter(
    store: circlePlacementStore,
  );
  final circleMemberships = AlphaCircleMembershipFacet();
  final circleGroups = AlphaCircleGroupFacet();
  final circleFiles = AlphaCircleFileFacet();
  final circleBehaviorFacts = AlphaCircleBehaviorFactWriter();
  final circleLifecycle = AlphaCircleLifecycleFacet();
  final rtcCalls = AlphaRtcCallSessionFacets();
  final hotQueries = AlphaHotQueryReader();
  final recentSearches = AlphaRecentSearchFacet();
  final searchFeedback = AlphaSearchFeedbackWriter();
  final intersections = AlphaIntersectionRepository();
  final userSettings = AlphaUserSettingsFacet();
  final accountSessions = AlphaAccountSessionFacet();
  final authenticationChallenges = AlphaAuthenticationChallengeFacet();
  final credentialBindings = AlphaCredentialBindingWriter();
  final profileCommands = AlphaProfileCommandWriter();
  final personas = AlphaPersonaFacet();
  final userProfiles = const MockUserProfileRepository();
  final contactDiscovery = AlphaContactDiscoveryFacet();
  final followingSubjects = AlphaFollowingSubjectFacet();
  final greetingRequests = AlphaGreetingRequestFacet();
  return <Override>[
    appDataSourceModeProvider.overrideWith(_AlphaMockDataSource.new),
    // content 域 production 组合根为 Remote-only；alpha 用 contract fixture
    // bundle 回放实现单点接管读/写/互动/配置、详情与作者页 reader、搜索与足迹。
    contentDiscoveryFeedQueryProvider.overrideWithValue(contentFixture),
    contentWriteRepositoryProvider.overrideWithValue(contentFixture),
    contentEngagementRepositoryProvider.overrideWithValue(contentFixture),
    contentConfigRepositoryProvider.overrideWithValue(contentFixture),
    contentRuntimeConfigProvider.overrideWithValue(
      buildAlphaContentRuntimeConfigDefaults(),
    ),
    imageEditorFilterRepositoryProvider.overrideWithValue(
      ImageEditorFilterRepository(
        catalogLoader: () async => imageEditorFilterConfigFromSnapshot(
          await filterCatalog.getActiveFilterCatalog(),
        ),
      ),
    ),
    behaviorRepositoryProvider.overrideWithValue(MockBehaviorRepository()),
    workBrowserContentPostDetailReaderProvider.overrideWithValue(
      contentFixture,
    ),
    globalSearchContentPostDetailReaderProvider.overrideWithValue(
      contentFixture,
    ),
    userProfileContentAuthorPostsReaderProvider.overrideWithValue(
      contentFixture,
    ),
    profileInteractionQueryFacetProvider.overrideWithValue(profileInteractions),
    profileInteractionReadFactAppendFacetProvider.overrideWithValue(
      profileInteractions,
    ),
    footprintRepositoryProvider.overrideWithValue(footprintFixture),
    intersectionRepositoryProvider.overrideWithValue(intersections),
    intersectionVisitWriterProvider.overrideWithValue(intersections),
    homepageFacetSetProvider.overrideWithValue(homepages),
    homepageIntroductionRepositoryProvider.overrideWith(
      (ref) => const MockHomepageIntroductionRepository(),
    ),
    homepageReviewCommandWriterProvider.overrideWithValue(homepageReviews),
    homepageReviewQueryProvider.overrideWithValue(homepageReviews),
    homepageSubjectFollowCommandWriterProvider.overrideWithValue(
      subjectFollows,
    ),
    personaRelationshipBlockWriterProvider.overrideWith(
      (ref, surface) => personaRelationships,
    ),
    blockedListQueryProvider.overrideWithValue(personaRelationships),
    circleRepositoryProvider.overrideWithValue(circles),
    circlesListDiscoveryFeedQueryProvider.overrideWithValue(circleQueries),
    circleDetailFeedQueryProvider.overrideWithValue(circleQueries),
    // user/profile production 组合根为 Remote-only；alpha 显式注入 contract
    // fixture 替身，生产依赖装配不再按 AppDataSourceMode 切换。
    personaQueryProvider.overrideWith((ref, surface) => personas),
    personaCommandWriterProvider.overrideWithValue(personas),
    profileCommandWriterProvider.overrideWithValue(profileCommands),
    userSettingsCommandWriterProvider.overrideWithValue(userSettings),
    userSettingsQueryReaderProvider.overrideWithValue(userSettings),
    accountSessionCommandWriterProvider.overrideWithValue(accountSessions),
    authenticationChallengeCommandWriterProvider.overrideWithValue(
      authenticationChallenges,
    ),
    appCredentialBindingCommandWriterProvider.overrideWithValue(
      credentialBindings,
    ),
    credentialBindingQueryProvider.overrideWithValue(credentialBindings),
    profileQueryProvider.overrideWith((ref, surface) => userProfiles),
    authorImpactQueryProvider.overrideWithValue(userProfiles),
    profileEditQueryProvider.overrideWith((ref, surface) => userProfiles),
    personaRelationshipQueryProvider.overrideWith(
      (ref, surface) => userProfiles,
    ),
    personaRelationshipCommandWriterProvider.overrideWith(
      (ref, surface) => userProfiles,
    ),
    contactDiscoveryRepositoryProvider.overrideWithValue(
      RemoteContactDiscoveryRepository(
        commandWriter: contactDiscovery,
        query: contactDiscovery,
      ),
    ),
    followingSubjectRepositoryProvider.overrideWithValue(
      RemoteFollowingSubjectRepository(
        query: followingSubjects,
        visitWriter: followingSubjects,
      ),
    ),
    relationshipCapabilityRepositoryProvider.overrideWithValue(
      RemoteRelationshipCapabilityRepository(query: personaRelationships),
    ),
    greetingRepositoryProvider.overrideWithValue(
      RemoteGreetingRepository(
        commandWriter: greetingRequests,
        query: greetingRequests,
      ),
    ),
    // search 链路仍消费同一 canonical Facet；alpha 只替换 fixture adapter。
    searchRepositoryProvider.overrideWith(
      (ref) => RemoteSearchRepository(remoteQuery: AlphaCanonicalSearchFacet()),
    ),
    searchHotQueryReaderProvider.overrideWithValue(hotQueries),
    recentSearchQueryProvider.overrideWithValue(recentSearches),
    recentSearchCommandWriterProvider.overrideWithValue(recentSearches),
    searchFeedbackCommandWriterProvider.overrideWithValue(searchFeedback),
    // tag 域两个查询 Facet 共用同一 fixture bundle 驱动的 Alpha 替身；
    // 反馈写面用进程内幂等替身。
    tagCatalogQueryProvider.overrideWith((ref) => AlphaTagFacet()),
    tagGraphQueryProvider.overrideWith((ref) => AlphaTagFacet()),
    tagFeedbackCommandWriterProvider.overrideWith(
      (ref) => AlphaTagFeedbackWriter(),
    ),
    // chat 域 production 组合根为 Remote-only；alpha repository 与发送命令共享
    // 同一个 pure state engine，避免列表、消息序列与幂等回执形成双状态。
    chatRepositoryCompositionProvider.overrideWithValue(chatRepository),
    realtimeConnectionManagerProvider.overrideWith(
      () => RealtimeConnectionNotifier(
        currentUserIdResolver: (ref) => ref.watch(currentUserIdProvider).trim(),
        delegateFactory:
            ({
              required ref,
              required onStateChanged,
              required currentUserIdResolver,
            }) => AlphaRealtimeConnectionDelegate(
              read: ref.read,
              invalidate: ref.invalidate,
              onStateChanged: onStateChanged,
            ),
      ),
    ),
    rtcCallLifecycleCommandWriterProvider.overrideWith(
      (ref, surface) => rtcCalls,
    ),
    rtcCallParticipantCommandWriterProvider.overrideWith(
      (ref, surface) => rtcCalls,
    ),
    rtcCallMediaControlWriterProvider.overrideWith((ref, surface) => rtcCalls),
    rtcCallScreenShareWriterProvider.overrideWith((ref, surface) => rtcCalls),
    rtcCallQueryProvider.overrideWith((ref, surface) => rtcCalls),
    nativeAuthBridgeProvider.overrideWithValue(const AlphaNativeAuthBridge()),
    createLocationNearbyReaderProvider.overrideWithValue(locationQuery),
    createLocationSearchReaderProvider.overrideWithValue(locationQuery),
    globalSearchLocationReaderProvider.overrideWithValue(locationQuery),
    locationGatewayProvider.overrideWithValue(const _AlphaLocationGateway()),
    homeFeedContentReportCommandWriterProvider.overrideWithValue(reportWriter),
    workBrowserContentReportCommandWriterProvider.overrideWithValue(
      reportWriter,
    ),
    userProfileContentReportCommandWriterProvider.overrideWithValue(
      reportWriter,
    ),
    contentPostReactionFacetProvider.overrideWithValue(postReactions),
    createContentPostPublicationWriterProvider.overrideWithValue(
      postPublication,
    ),
    workBrowserContentCommentFacetProvider.overrideWithValue(comments),
    profileCommentsContentCommentFacetProvider.overrideWithValue(comments),
    appMessageQueryProvider.overrideWithValue(appMessages),
    appMessageCommandWriterProvider.overrideWithValue(appMessages),
    chatMessageCommandWriterProvider.overrideWithValue(chatMessages),
    createContentMediaFacetProvider.overrideWithValue(media),
    homeFeedContentMediaFacetProvider.overrideWithValue(media),
    workBrowserContentMediaFacetProvider.overrideWithValue(media),
    chatDetailContentMediaFacetProvider.overrideWithValue(media),
    profileEditContentMediaFacetProvider.overrideWithValue(media),
    circleDetailContentMediaFacetProvider.overrideWithValue(media),
    profileMediaUploadGatewayProvider.overrideWithValue(
      const _AlphaProfileMediaUploadGateway(),
    ),
    contentMediaStreamObjectUploadProvider.overrideWithValue(
      _alphaContentMediaStreamObjectUpload,
    ),
    contentMediaSourceReaderProvider.overrideWithValue(
      const LocalContentMediaSourceReader(),
    ),
    homeFeedContentOutboundShareWriterProvider.overrideWithValue(
      outboundShares,
    ),
    workBrowserContentOutboundShareWriterProvider.overrideWithValue(
      outboundShares,
    ),
    homeFeedCirclePostPlacementWriterProvider.overrideWithValue(
      circlePostPlacements,
    ),
    workBrowserCirclePostPlacementWriterProvider.overrideWithValue(
      circlePostPlacements,
    ),
    circleDetailPostPlacementCommandWriterProvider.overrideWithValue(
      circlePostPlacements,
    ),
    createWorkspaceCirclePostPlacementWriterProvider.overrideWithValue(
      circlePostPlacements,
    ),
    circleDetailMembershipCommandWriterProvider.overrideWithValue(
      circleMemberships,
    ),
    circleDetailMembershipQueryProvider.overrideWithValue(circleMemberships),
    circleStatsMembershipQueryProvider.overrideWithValue(circleMemberships),
    homeFeedCircleMembershipQueryProvider.overrideWithValue(circleMemberships),
    workBrowserCircleMembershipQueryProvider.overrideWithValue(
      circleMemberships,
    ),
    userProfileCircleMembershipQueryProvider.overrideWithValue(
      circleMemberships,
    ),
    circleDetailGroupQueryProvider.overrideWithValue(circleGroups),
    circleDetailFileCommandWriterProvider.overrideWithValue(circleFiles),
    circleDetailFileQueryProvider.overrideWithValue(circleFiles),
    circleStatsGroupQueryProvider.overrideWithValue(circleGroups),
    globalSearchCircleGroupQueryProvider.overrideWithValue(circleGroups),
    circleDetailBehaviorFactWriterProvider.overrideWithValue(
      circleBehaviorFacts,
    ),
    circlesListCircleLifecycleCommandWriterProvider.overrideWithValue(
      circleLifecycle,
    ),
    circleDetailCircleLifecycleCommandWriterProvider.overrideWithValue(
      circleLifecycle,
    ),
    circleDetailCircleConfigurationCommandWriterProvider.overrideWithValue(
      circleLifecycle,
    ),
  ];
}

/// Alpha-only native-auth fixture. It is reachable exclusively from the
/// independent alpha runner and can never be selected by production DI.
final class AlphaNativeAuthBridge implements NativeAuthBridge {
  const AlphaNativeAuthBridge();

  static const _socialProviders = <NativeAuthProvider>{
    NativeAuthProvider.wechat,
    NativeAuthProvider.alipay,
    NativeAuthProvider.qq,
  };

  @override
  Future<NativeAuthCapability> getCapability(
    NativeAuthProvider provider,
  ) async {
    final available = _socialProviders.contains(provider);
    return NativeAuthCapability(
      provider: provider,
      availability: available
          ? NativeAuthAvailability.available
          : NativeAuthAvailability.unsupportedPlatform,
      reason: available ? 'alpha_fixture' : 'unsupported_in_alpha',
    );
  }

  @override
  Future<NativeAuthResult> signIn(
    NativeAuthProvider provider, {
    String authorizationPayload = '',
  }) async {
    if (!_socialProviders.contains(provider)) {
      throw StateError('${provider.name} alpha auth fixture is unavailable');
    }
    return NativeAuthResult(
      provider: provider,
      ticket: 'alpha-fixture-${provider.name}',
      displayLabel: 'alpha-${provider.name}',
    );
  }

  @override
  Future<NativeAuthResult> signInWithPasskey({
    String? relyingPartyId,
    String? challenge,
  }) async {
    throw StateError('passkey alpha auth fixture is unavailable');
  }
}

Future<void> _alphaContentMediaStreamObjectUpload(
  Uri uploadUri,
  Stream<List<int>> bytes, {
  required int contentLength,
  required String contentType,
  required String expectedSha256,
  Future<void>? abortTrigger,
}) async {
  if (uploadUri.host != 'alpha-upload.invalid' ||
      contentLength <= 0 ||
      contentType.trim().isEmpty) {
    throw StateError('invalid alpha media stream upload fixture');
  }
  var observed = 0;
  final observedBytes = <int>[];
  await for (final chunk in bytes) {
    observed += chunk.length;
    observedBytes.addAll(chunk);
  }
  if (observed != contentLength ||
      !_matchesExpectedSha256(observedBytes, expectedSha256)) {
    throw StateError('alpha media stream byte contract mismatch');
  }
}

bool _matchesExpectedSha256(List<int> bytes, String expectedSha256) {
  final normalized = expectedSha256.trim().toLowerCase().replaceFirst(
    'sha256:',
    '',
  );
  return normalized.length == 64 &&
      sha256.convert(bytes).toString() == normalized;
}

final class _AlphaProfileMediaUploadGateway
    implements ProfileMediaUploadGateway {
  const _AlphaProfileMediaUploadGateway();

  @override
  Future<ProfileMediaUploadResult> uploadImage({
    required String localPath,
    required ProfileMediaTarget target,
  }) async {
    final path = localPath.trim();
    if (path.isEmpty) throw StateError('alpha profile media path is empty');
    final scope = target == ProfileMediaTarget.avatar ? 'avatar' : 'cover';
    return ProfileMediaUploadResult(
      assetId: 'alpha_profile_${scope}_${path.hashCode.abs()}',
      cdnUrl: 'https://alpha-cdn.invalid/profile/$scope',
    );
  }
}

final class _AlphaMockDataSource extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;

  @override
  void setMode(AppDataSourceMode mode) {
    if (mode == AppDataSourceMode.mock) {
      super.setMode(mode);
    }
  }
}

final class _AlphaLocationGateway implements LocationGateway {
  const _AlphaLocationGateway();

  @override
  Future<LocationAccessResult> ensureAccess() async {
    return const LocationAccessResult(
      permission: LocationPermissionResult.granted,
      position: AppGeoPosition(latitude: 30.2431, longitude: 120.1505),
    );
  }
}
