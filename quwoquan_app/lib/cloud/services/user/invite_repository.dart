import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/invite_accept_response_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/invite_generate_response_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/invite_record_list_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// InviteRepository：邀请归因与生命周期管理。
abstract class InviteRepository {
  /// 为指定分身生成邀请链接。
  Future<InviteGenerateResponseDto> generate({
    required String subAccountId,
    required String channel,
    String? inviteePhone,
  });

  /// 列出分身发出的邀请列表。
  Future<List<InviteRecordListItemDto>> listByPersona({
    required String subAccountId,
    String? statusFilter,
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 通过邀请码获取邀请详情（公开接口，无需鉴权）。
  Future<InviteRecordListItemDto?> getByCode(String code);

  /// 接受邀请（被邀请方调用）。
  Future<InviteAcceptResponseDto> accept(String code);
}

class MockInviteRepository implements InviteRepository {
  @override
  Future<InviteGenerateResponseDto> generate({
    required String subAccountId,
    required String channel,
    String? inviteePhone,
  }) async {
    await Future.delayed(const Duration(milliseconds: 200));
    return InviteGenerateResponseDto.fromMap(<String, dynamic>{
      'id': 'mock_invite_${DateTime.now().millisecondsSinceEpoch}',
      'linkCode': 'MOCK${subAccountId.hashCode.abs() % 10000}',
      'inviterSubAccountId': subAccountId,
      'channel': channel,
      'status': 'pending',
    });
  }

  @override
  Future<List<InviteRecordListItemDto>> listByPersona({
    required String subAccountId,
    String? statusFilter,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return [];
  }

  @override
  Future<InviteRecordListItemDto?> getByCode(String code) async {
    return null;
  }

  @override
  Future<InviteAcceptResponseDto> accept(String code) async {
    return InviteAcceptResponseDto.fromMap(<String, dynamic>{
      'linkCode': code,
      'status': 'accepted',
    });
  }
}

class RemoteInviteRepository implements InviteRepository {
  RemoteInviteRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _client = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  @override
  Future<InviteGenerateResponseDto> generate({
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
    return InviteGenerateResponseDto.fromMap(
      CloudResponseDecoder.asObject(
        resp,
        context: UserRequestPageIds.generateInvite,
      ),
    );
  }

  @override
  Future<List<InviteRecordListItemDto>> listByPersona({
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
    final uri = _uri(
      UserApiMetadata.listMyInvitesPath,
    ).replace(queryParameters: params);
    final resp = await _client.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.listMyInvites),
    );
    final data = CloudResponseDecoder.asObject(
      resp,
      context: UserRequestPageIds.listMyInvites,
    );
    return CloudResponseDecoder.mapList(
      data,
      'invites',
    ).map(InviteRecordListItemDto.fromMap).toList(growable: false);
  }

  @override
  Future<InviteRecordListItemDto?> getByCode(String code) async {
    try {
      final resp = await _client.getJson(
        _uri(UserApiMetadata.getInviteByCodePath(linkCode: code)),
        headers: CloudRequestHeaders.forPage(
          UserRequestPageIds.getInviteByCode,
        ),
      );
      return InviteRecordListItemDto.fromMap(
        CloudResponseDecoder.asObject(
          resp,
          context: UserRequestPageIds.getInviteByCode,
        ),
      );
    } catch (_) {
      return null;
    }
  }

  @override
  Future<InviteAcceptResponseDto> accept(String code) async {
    final resp = await _client.postJson(
      _uri(UserApiMetadata.acceptInvitePath(linkCode: code)),
      headers: CloudRequestHeaders.forPage(UserRequestPageIds.acceptInvite),
      body: {},
    );
    return InviteAcceptResponseDto.fromMap(
      CloudResponseDecoder.asObject(
        resp,
        context: UserRequestPageIds.acceptInvite,
      ),
    );
  }
}
