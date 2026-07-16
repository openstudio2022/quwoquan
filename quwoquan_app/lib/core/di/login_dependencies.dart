import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';
import 'package:quwoquan_app/cloud/services/user/social_authorization_repository.dart';
import 'package:quwoquan_app/core/auth/one_tap_login_channel.dart';
import 'package:quwoquan_app/core/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/core/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';

/// 登录能力的 production 组合入口，仅允许 Remote。
/// Alpha contract fixture 由独立 runner 显式 override，不能通过环境或数据源开关触发。
final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return RemoteAuthRepository(httpClient: ref.watch(cloudHttpClientProvider));
});

/// Public anonymous bootstrap has no prior bearer session by contract.
/// Keep its type narrow so a session bootstrap caller cannot accidentally use
/// post-login account operations through this dependency.
final anonymousLoginGatewayProvider = Provider<AnonymousLoginGateway>((ref) {
  return RemoteAuthRepository(
    httpClient: ref.watch(unauthenticatedCloudHttpClientProvider),
  );
});

final oneTapLoginClientProvider = Provider<OneTapLoginClient>((ref) {
  return MethodChannelOneTapLoginClient();
});

final socialAuthorizationRepositoryProvider =
    Provider<SocialAuthorizationRepository>((ref) {
      return RemoteSocialAuthorizationRepository(
        httpClient: ref.watch(cloudHttpClientProvider),
      );
    });

/// 登录页专用的轻量漏斗组合入口。
///
/// 不依赖全应用 Provider 聚合图；事件 schema、脱敏与上报实现仍复用统一
/// [JourneyEventTracker] / [OpsEventRepository]。
final loginJourneyEventTrackerProvider = Provider<JourneyEventTracker>((ref) {
  return JourneyEventTracker(
    eventRepository: ref.watch(opsEventRepositoryProvider),
  );
});
