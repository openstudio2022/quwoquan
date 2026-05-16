import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';

const int _kUserSyncPullDefaultLimit = 200;

class UserSyncPatch {
  const UserSyncPatch({
    required this.syncSeq,
    required this.type,
    required this.userId,
    required this.payload,
  });

  final int syncSeq;
  final String type;
  final String userId;
  final Map<String, dynamic> payload;

  factory UserSyncPatch.fromMap(Map<String, dynamic> map) {
    return UserSyncPatch(
      syncSeq: (map['syncSeq'] as num?)?.toInt() ?? 0,
      type: map['type']?.toString() ?? '',
      userId: map['userId']?.toString() ?? '',
      payload: Map<String, dynamic>.from(
        map['payload'] as Map? ?? const <String, dynamic>{},
      ),
    );
  }
}

class UserSyncPullResult {
  const UserSyncPullResult({
    required this.patches,
    required this.latestSyncSeq,
    required this.hasMore,
    required this.requiresResync,
  });

  final List<UserSyncPatch> patches;
  final int latestSyncSeq;
  final bool hasMore;
  final bool requiresResync;

  factory UserSyncPullResult.fromMap(Map<String, dynamic> map) {
    final rawPatches = (map['patches'] as List?) ?? const <dynamic>[];
    return UserSyncPullResult(
      patches: rawPatches
          .whereType<Map>()
          .map((item) => UserSyncPatch.fromMap(Map<String, dynamic>.from(item)))
          .toList(growable: false),
      latestSyncSeq: (map['latestSyncSeq'] as num?)?.toInt() ?? 0,
      hasMore: map['hasMore'] as bool? ?? false,
      requiresResync: map['requiresResync'] as bool? ?? false,
    );
  }
}

abstract class UserSyncRepository {
  Future<UserSyncPullResult> pull({
    required int afterSeq,
    int limit = _kUserSyncPullDefaultLimit,
  });
}

class MockUserSyncRepository implements UserSyncRepository {
  @override
  Future<UserSyncPullResult> pull({
    required int afterSeq,
    int limit = _kUserSyncPullDefaultLimit,
  }) async {
    return const UserSyncPullResult(
      patches: <UserSyncPatch>[],
      latestSyncSeq: 0,
      hasMore: false,
      requiresResync: false,
    );
  }
}

typedef UserSyncRemoteMergeRequestContext =
    Future<Map<String, String>> Function(Map<String, String> baseHeaders);

class RemoteUserSyncRepository implements UserSyncRepository {
  RemoteUserSyncRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
    UserSyncRemoteMergeRequestContext? mergeRequestContext,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
       _mergeRequestContext = mergeRequestContext;

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final UserSyncRemoteMergeRequestContext? _mergeRequestContext;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Future<Map<String, String>> _resolveHeaders(String clientPageId) async {
    final base = CloudRequestHeaders.forPage(clientPageId);
    final merger = _mergeRequestContext;
    if (merger == null) {
      return base;
    }
    return merger(base);
  }

  @override
  Future<UserSyncPullResult> pull({
    required int afterSeq,
    int limit = _kUserSyncPullDefaultLimit,
  }) async {
    final result = await _httpClient.postJsonObject(
      _uri(UserApiMetadata.pullUserSyncPath),
      headers: await _resolveHeaders(UserRequestPageIds.pullUserSync),
      body: <String, dynamic>{'afterSeq': afterSeq, 'limit': limit},
      context: UserRequestPageIds.pullUserSync,
    );
    return UserSyncPullResult.fromMap(result);
  }
}
