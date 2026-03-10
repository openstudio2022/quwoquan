import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// InviteRepository：邀请归因与生命周期管理。
abstract class InviteRepository {
  /// 为指定子账号生成邀请链接。
  Future<Map<String, dynamic>> generate({
    required String subAccountId,
    required String channel,
    String? inviteePhone,
  });

  /// 列出子账号发出的邀请列表。
  Future<List<Map<String, dynamic>>> listBySubAccount({
    required String subAccountId,
    String? statusFilter,
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 通过邀请码获取邀请详情（公开接口，无需鉴权）。
  Future<Map<String, dynamic>?> getByCode(String code);

  /// 接受邀请（被邀请方调用）。
  Future<Map<String, dynamic>> accept(String code);
}

class MockInviteRepository implements InviteRepository {
  @override
  Future<Map<String, dynamic>> generate({
    required String subAccountId,
    required String channel,
    String? inviteePhone,
  }) async {
    await Future.delayed(const Duration(milliseconds: 200));
    return {
      'id': 'mock_invite_${DateTime.now().millisecondsSinceEpoch}',
      'linkCode': 'MOCK${subAccountId.hashCode.abs() % 10000}',
      'inviterSubAccountId': subAccountId,
      'channel': channel,
      'status': 'pending',
    };
  }

  @override
  Future<List<Map<String, dynamic>>> listBySubAccount({
    required String subAccountId,
    String? statusFilter,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return [];
  }

  @override
  Future<Map<String, dynamic>?> getByCode(String code) async {
    return null;
  }

  @override
  Future<Map<String, dynamic>> accept(String code) async {
    return {'linkCode': code, 'status': 'accepted'};
  }
}

class RemoteInviteRepository implements InviteRepository {
  RemoteInviteRepository({CloudHttpClient? httpClient, String? baseUrl})
      : _client = httpClient ?? CloudHttpClient(client: http.Client()),
        _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  @override
  Future<Map<String, dynamic>> generate({
    required String subAccountId,
    required String channel,
    String? inviteePhone,
  }) async {
    final body = <String, dynamic>{
      'subAccountId': subAccountId,
      'channel': channel,
    };
    if (inviteePhone != null) {
      body['inviteePhone'] = inviteePhone;
    }
    final resp = await _client.postJson(
      _uri(UserApiMetadata.generateInvitePath),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.generateInvite),
      body: body,
    );
    return resp as Map<String, dynamic>;
  }

  @override
  Future<List<Map<String, dynamic>>> listBySubAccount({
    required String subAccountId,
    String? statusFilter,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final params = <String, String>{
      'subAccountId': subAccountId,
      'limit': '$limit',
    };
    if (statusFilter != null) {
      params['status'] = statusFilter;
    }
    final uri = _uri(UserApiMetadata.listMyInvitesPath).replace(
      queryParameters: params,
    );
    final resp = await _client.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listMyInvites),
    );
    final data = resp as Map<String, dynamic>;
    return (data['invites'] as List<dynamic>).cast<Map<String, dynamic>>();
  }

  @override
  Future<Map<String, dynamic>?> getByCode(String code) async {
    try {
      final resp = await _client.getJson(
        _uri(UserApiMetadata.getInviteByCodePath(linkCode: code)),
        headers: CloudRequestHeaders.forPage(UserRequestPageIds.getInviteByCode),
      );
      return resp as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  @override
  Future<Map<String, dynamic>> accept(String code) async {
    final resp = await _client.postJson(
      _uri(UserApiMetadata.acceptInvitePath(linkCode: code)),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.acceptInvite),
      body: {},
    );
    return resp as Map<String, dynamic>;
  }
}
