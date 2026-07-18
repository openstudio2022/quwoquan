import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/core/platform/location/location_gateway.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/cloud/services/user/profile_media_upload_gateway.dart';
import 'package:quwoquan_app/cloud/remote/content/media/local_media_upload_source.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

import 'alpha_auth_adapters.dart';
import 'alpha_realtime_connection_delegate.dart';

/// Alpha-only dependency composition. Production never imports this runner.
List<Override> buildAlphaCloudOverrides() {
  final locationQuery = AlphaLocationQueryAdapter();
  final reportWriter = AlphaContentReportAdapter();
  final comments = AlphaContentCommentFacet();
  final postReactions = AlphaContentPostReactionFacet();
  final postPublication = AlphaContentPostPublicationWriter();
  final appMessages = AlphaAppMessageAdapter();
  final chatMessages = AlphaChatMessageCommandWriter();
  final media = AlphaContentMediaFacet();
  final outboundShares = AlphaContentOutboundShareWriter();
  final circlePostPlacements = AlphaCirclePostPlacementWriter();
  final circleMemberships = AlphaCircleMembershipFacet();
  final circleGroups = AlphaCircleGroupFacet();
  final circleGroupMemberships = AlphaCircleGroupMembershipFacet();
  final circleFiles = AlphaCircleFileFacet();
  final circleBehaviorFacts = AlphaCircleBehaviorFactWriter();
  return <Override>[
    appDataSourceModeProvider.overrideWith(_AlphaMockDataSource.new),
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
    authRepositoryProvider.overrideWithValue(AlphaAuthRepository()),
    socialAuthorizationRepositoryProvider.overrideWithValue(
      const AlphaSocialAuthorizationRepository(),
    ),
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
    contentMediaObjectUploadProvider.overrideWithValue(
      _alphaContentMediaObjectUpload,
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
    createWorkspaceCirclePostPlacementWriterProvider.overrideWithValue(
      circlePostPlacements,
    ),
    circleDetailMembershipCommandWriterProvider.overrideWithValue(
      circleMemberships,
    ),
    circleDetailMembershipQueryProvider.overrideWithValue(circleMemberships),
    circleStatsMembershipCommandWriterProvider.overrideWithValue(
      circleMemberships,
    ),
    circleStatsMembershipQueryProvider.overrideWithValue(circleMemberships),
    homeFeedCircleMembershipQueryProvider.overrideWithValue(circleMemberships),
    workBrowserCircleMembershipQueryProvider.overrideWithValue(
      circleMemberships,
    ),
    userProfileCircleMembershipQueryProvider.overrideWithValue(
      circleMemberships,
    ),
    circleDetailGroupCommandWriterProvider.overrideWithValue(circleGroups),
    circleDetailGroupQueryProvider.overrideWithValue(circleGroups),
    circleDetailFileCommandWriterProvider.overrideWithValue(circleFiles),
    circleDetailFileQueryProvider.overrideWithValue(circleFiles),
    circleStatsGroupQueryProvider.overrideWithValue(circleGroups),
    globalSearchCircleGroupQueryProvider.overrideWithValue(circleGroups),
    circleDetailGroupMembershipCommandWriterProvider.overrideWithValue(
      circleGroupMemberships,
    ),
    circleDetailGroupMembershipQueryProvider.overrideWithValue(
      circleGroupMemberships,
    ),
    circleStatsGroupMembershipCommandWriterProvider.overrideWithValue(
      circleGroupMemberships,
    ),
    circleStatsGroupMembershipQueryProvider.overrideWithValue(
      circleGroupMemberships,
    ),
    circleDetailBehaviorFactWriterProvider.overrideWithValue(
      circleBehaviorFacts,
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

Future<void> _alphaContentMediaObjectUpload(
  Uri uploadUri,
  List<int> bytes, {
  required String contentType,
  required String expectedSha256,
}) async {
  if (uploadUri.host != 'alpha-upload.invalid' ||
      bytes.isEmpty ||
      contentType.trim().isEmpty ||
      !_matchesExpectedSha256(bytes, expectedSha256)) {
    throw StateError('invalid alpha media object upload fixture');
  }
}

Future<void> _alphaContentMediaStreamObjectUpload(
  Uri uploadUri,
  Stream<List<int>> bytes, {
  required int contentLength,
  required String contentType,
  required String expectedSha256,
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
