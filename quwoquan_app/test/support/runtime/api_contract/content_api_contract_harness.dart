import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_command_remote.dart';
import 'package:quwoquan_app/service/content_service/content/comment/adapters/comment_facets_remote.dart';
import 'package:quwoquan_app/service/content_service/content/content_reaction/adapters/post_reaction_facets_remote.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_publication_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_delete_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_remote.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/adapters/profile_interaction_activity_remote.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_read_fact/adapters/profile_interaction_read_fact_remote.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/media_asset_remote.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/media_upload_session_remote.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/adapters/original_access_quota_remote.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/adapters/report_command_remote.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'api_contract_environment.dart';
import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

const contentApiContractDeviceId = 'content-api-contract-device';

/// Real generated-client -> production object adapters -> process harness.
final class ContentApiContractHarness {
  ContentApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this._accountLifecycle,
    required this.feed,
    required this.posts,
    required this.postDeletion,
    required this.publication,
    required this.comments,
    required this.reactions,
    required this.profileInteractions,
    required this.profileInteractionReads,
    required this.behaviors,
    required this.reports,
    required this.mediaUploads,
    required this.mediaAssets,
    required this.originalAccess,
    required this.session,
  });

  static Future<ContentApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: API_CONTRACT_BASE_URL not set');
    }
    ApiContractEnvironment.ensureLocalTlsRootTrusted();
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    late ContentApiContractHarness harness;
    const clientContext = _ContentApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: clientContext,
      telemetrySink: telemetry.sink,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.values.firstWhere(
          (candidate) => candidate.name == _apiContractEnv,
          orElse: () => throw StateError(
            'Unsupported API_CONTRACT_ENV: $_apiContractEnv',
          ),
        ),
        gatewayBaseUri: Uri.parse(_apiBase),
      ),
    );

    try {
      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: contentApiContractDeviceId,
          ),
        ),
      );
      final session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'content-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'content-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      CloudOperationInvocationContext queryContext(String clientPageId) {
        final surface = switch (clientPageId) {
          ContentRequestPageIds.getFeed => AppUiSurfaces.homeFeed,
          ContentRequestPageIds.reportBehaviors =>
            AppUiSurfaces.interestOnboarding,
          ContentRequestPageIds.getPost => AppUiSurfaces.workBrowser,
          ContentRequestPageIds.listUserPosts => AppUiSurfaces.userProfile,
          ContentRequestPageIds.deletePost => AppUiSurfaces.workBrowser,
          ContentRequestPageIds.createReport => AppUiSurfaces.homeFeed,
          _ => throw StateError(
            'Unsupported Content API contract clientPageId: $clientPageId',
          ),
        };
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          actor: CloudOperationActorContext(
            accountId: session.ownerId,
            personaId: session.activePersona?.personaId,
            deviceActorId: contentApiContractDeviceId,
          ),
        );
      }

      CloudOperationInvocationContext commandContext(
        String clientPageId,
        String idempotencyKey,
      ) {
        final surface = switch (clientPageId) {
          ContentRequestPageIds.submitPostPublication =>
            AppUiSurfaces.createWorkspace,
          ContentRequestPageIds.deletePost => AppUiSurfaces.workBrowser,
          _ => AppUiSurfaces.homeFeed,
        };
        final base = queryContext(
          clientPageId == ContentRequestPageIds.submitPostPublication
              ? ContentRequestPageIds.getFeed
              : clientPageId,
        );
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: idempotencyKey,
          actor: base.actor,
        );
      }

      CloudOperationInvocationContext commentContext(
        String clientPageId, {
        required bool command,
      }) => harness._commentInvocationContext(clientPageId, command: command);

      CloudOperationInvocationContext profileInteractionContext(
        String clientPageId,
      ) => harness._profileInteractionInvocationContext(clientPageId);

      CloudOperationInvocationContext mediaContext(
        String clientPageId, {
        required bool command,
      }) => harness._mediaInvocationContext(clientPageId, command: command);

      harness = ContentApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        accountLifecycle: RemoteAccountLifecycleCommandWriter(
          client: client,
          invocationContext: (clientPageId) =>
              harness._accountInvocationContext(clientPageId),
        ),
        feed: RemoteContentDiscoveryFeedQuery(
          client: client,
          invocationContext: queryContext,
          blockedKeywordsLoader: () async => const <String>[],
        ),
        posts: RemoteContentPostReaderAdapter(
          client: client,
          invocationContext: queryContext,
        ),
        postDeletion: RemoteContentPostDeleteCommandWriter(
          client: client,
          invocationContext: commandContext,
        ),
        publication: RemoteContentPostPublicationWriter(
          client: client,
          invocationContext: commandContext,
        ),
        comments: RemoteContentCommentFacet(
          client: client,
          invocationContext: commentContext,
        ),
        reactions: RemoteContentPostReactionFacet(
          client: client,
          invocationContext: commentContext,
        ),
        profileInteractions: RemoteProfileInteractionActivityQuery(
          client: client,
          invocationContext: profileInteractionContext,
        ),
        profileInteractionReads: RemoteProfileInteractionReadFactWriter(
          client: client,
          invocationContext: profileInteractionContext,
        ),
        behaviors: RemoteContentBehaviorCommandAdapter(
          client: client,
          invocationContext: queryContext,
        ),
        reports: RemoteContentReportAdapter(
          client: client,
          invocationContext: queryContext,
        ),
        mediaUploads: RemoteContentMediaUploadSessionAdapter(
          client: client,
          invocationContext: mediaContext,
        ),
        mediaAssets: RemoteContentMediaAssetAdapter(
          client: client,
          invocationContext: mediaContext,
        ),
        originalAccess: RemoteContentOriginalAccessQuotaWriter(
          client: client,
          invocationContext: mediaContext,
        ),
        session: session,
      );
      return harness;
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  final RemoteContentDiscoveryFeedQuery feed;
  final RemoteContentPostReaderAdapter posts;
  final RemoteContentPostDeleteCommandWriter postDeletion;
  final RemoteContentPostPublicationWriter publication;
  final RemoteContentCommentFacet comments;
  final RemoteContentPostReactionFacet reactions;
  final RemoteProfileInteractionActivityQuery profileInteractions;
  final RemoteProfileInteractionReadFactWriter profileInteractionReads;
  final RemoteContentBehaviorCommandAdapter behaviors;
  final RemoteContentReportAdapter reports;
  final RemoteContentMediaUploadSessionAdapter mediaUploads;
  final RemoteContentMediaAssetAdapter mediaAssets;
  final RemoteContentOriginalAccessQuotaWriter originalAccess;
  final AuthSessionGrant session;
  String? _activeIdempotencyKey;
  var _closed = false;

  Future<T> withIdempotencyKey<T>(
    String idempotencyKey,
    Future<T> Function() operation,
  ) async {
    final normalized = idempotencyKey.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(idempotencyKey, 'idempotencyKey');
    }
    if (_activeIdempotencyKey != null) {
      throw StateError('Content API contract commands must be sequential');
    }
    _activeIdempotencyKey = normalized;
    try {
      return await operation();
    } finally {
      _activeIdempotencyKey = null;
    }
  }

  Future<void> close() async {
    if (_closed) {
      return;
    }
    _closed = true;
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'content-api-cleanup-${session.ownerId}',
        ),
      );
      await telemetry.waitForEvents(minimumCount: 1);
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }

  CloudOperationInvocationContext _commentInvocationContext(
    String clientPageId, {
    required bool command,
  }) {
    switch (clientPageId) {
      case ContentRequestPageIds.createComment:
      case ContentRequestPageIds.deleteComment:
      case ContentRequestPageIds.pinComment:
      case ContentRequestPageIds.unpinComment:
      case ContentRequestPageIds.listComments:
      case ContentRequestPageIds.listCommentReplies:
      case ContentRequestPageIds.listCommentsByAuthor:
      case ContentRequestPageIds.listCommentsForPostAuthor:
      case ContentRequestPageIds.reactToComment:
      case ContentRequestPageIds.getContentReactionState:
      case ContentRequestPageIds.likePost:
      case ContentRequestPageIds.unlikePost:
        break;
      default:
        throw StateError(
          'Unsupported Content comment/reaction clientPageId: $clientPageId',
        );
    }
    final idempotencyKey = command ? _activeIdempotencyKey : null;
    if (command && idempotencyKey == null) {
      throw StateError(
        'Content comment/reaction command requires an explicit idempotency key',
      );
    }
    return CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.workBrowser.id,
      routeId: AppUiSurfaces.workBrowser.routeId,
      clientPageId: clientPageId,
      idempotencyKey: idempotencyKey,
      actor: CloudOperationActorContext(
        accountId: session.ownerId,
        personaId: session.activePersona?.personaId,
        deviceActorId: contentApiContractDeviceId,
      ),
    );
  }

  CloudOperationInvocationContext _accountInvocationContext(
    String clientPageId,
  ) {
    if (clientPageId != UserRequestPageIds.closeAccount) {
      throw StateError(
        'Unsupported Content account cleanup clientPageId: $clientPageId',
      );
    }
    return CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.settingsAccountSecurity.id,
      routeId: AppUiSurfaces.settingsAccountSecurity.routeId,
      clientPageId: clientPageId,
      idempotencyKey: 'content-api-account-cleanup-${session.ownerId}',
      actor: CloudOperationActorContext(
        accountId: session.ownerId,
        personaId: session.activePersona?.personaId,
        deviceActorId: contentApiContractDeviceId,
      ),
    );
  }

  CloudOperationInvocationContext _mediaInvocationContext(
    String clientPageId, {
    required bool command,
  }) {
    final surface = switch (clientPageId) {
      ContentRequestPageIds.initMediaUpload ||
      ContentRequestPageIds.completeMediaUpload ||
      ContentRequestPageIds.abortMediaUpload => AppUiSurfaces.createWorkspace,
      ContentRequestPageIds.getMediaUploadSession ||
      ContentRequestPageIds.getMediaAsset ||
      ContentRequestPageIds.reserveOriginalImageAccessGrant =>
        AppUiSurfaces.workBrowser,
      _ => throw StateError(
        'Unsupported Content media clientPageId: $clientPageId',
      ),
    };
    final idempotencyKey = command ? _activeIdempotencyKey : null;
    if (command && idempotencyKey == null) {
      throw StateError(
        'Content media command requires an explicit idempotency key',
      );
    }
    return CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      idempotencyKey: idempotencyKey,
      actor: CloudOperationActorContext(
        accountId: session.ownerId,
        personaId: session.activePersona?.personaId,
        deviceActorId: contentApiContractDeviceId,
      ),
    );
  }

  CloudOperationInvocationContext _profileInteractionInvocationContext(
    String clientPageId,
  ) {
    switch (clientPageId) {
      case ContentRequestPageIds.listProfileInteractionActivitiesReceived:
      case ContentRequestPageIds.listProfileInteractionActivitiesSent:
      case ContentRequestPageIds.appendProfileInteractionReadFact:
        break;
      default:
        throw StateError(
          'Unsupported Content profile interaction clientPageId: '
          '$clientPageId',
        );
    }
    return CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.profileHome.id,
      routeId: AppUiSurfaces.profileHome.routeId,
      clientPageId: clientPageId,
      actor: CloudOperationActorContext(
        accountId: session.ownerId,
        personaId: session.activePersona?.personaId,
        deviceActorId: contentApiContractDeviceId,
      ),
    );
  }
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _ContentApiClientContext implements CloudClientContextProvider {
  const _ContentApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'content-api-contract',
      deviceActorId: contentApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
