import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/contact_discovery_match_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// 一次通讯录匹配的结果视图（POST initiate / GET latest 同构）。
///
/// `matches` 是富化投影（[ContactDiscoveryMatchWireDto]）：回显发起者自己上传的
/// `hashedPhone`（用于把命中映射回本机联系人姓名）+ 精简 profile + viewer 维度的
/// `relationshipCapability`（驱动「添加 / 已添加」按钮）。`matchedSubAccountIds` 是
/// 隐私基线（即使富化失败也保证返回）。对方手机号原文端云均不出现。
class ContactDiscoveryResultView {
  const ContactDiscoveryResultView({
    required this.id,
    required this.status,
    required this.matchedSubAccountIds,
    required this.matchCount,
    required this.matches,
  });

  final String id;
  final String status;
  final List<String> matchedSubAccountIds;
  final int matchCount;
  final List<ContactDiscoveryMatchWireDto> matches;

  static const ContactDiscoveryResultView empty = ContactDiscoveryResultView(
    id: '',
    status: 'completed',
    matchedSubAccountIds: <String>[],
    matchCount: 0,
    matches: <ContactDiscoveryMatchWireDto>[],
  );

  factory ContactDiscoveryResultView.fromMap(Map<String, dynamic> m) {
    final rawMatchedIds = m['matchedSubAccountIds'];
    final matchedIds = rawMatchedIds is List
        ? rawMatchedIds
              .map((e) => e.toString())
              .where((e) => e.isNotEmpty)
              .toList(growable: false)
        : const <String>[];
    final matches = CloudResponseDecoder.mapList(m, 'matches')
        .map(ContactDiscoveryMatchWireDto.fromMap)
        .toList(growable: false);
    return ContactDiscoveryResultView(
      id: m['id']?.toString() ?? '',
      status: m['status']?.toString() ?? 'completed',
      matchedSubAccountIds: matchedIds,
      matchCount: (m['matchCount'] as num?)?.toInt() ?? matches.length,
      matches: matches,
    );
  }
}

/// ContactDiscoveryRepository：通讯录批量哈希匹配（窄接口）。
///
/// 端侧上传的 `hashedPhones` 必须由共享 `contact_hash_service`（与服务端
/// `phonematch.Hash` 同算法：规范化 E.164 → +salt → SHA256）派生，匹配只在哈希域完成。
abstract class ContactDiscoveryRepository {
  /// 发起一次通讯录匹配，返回命中结果（含富化 matches）。
  Future<ContactDiscoveryResultView> initiate(List<String> hashedPhones);

  /// 读取最近一次匹配结果；无记录返回 null。
  Future<ContactDiscoveryResultView?> getLatest();

  /// 关闭/忽略一次匹配记录。
  Future<void> dismiss(String id);
}

/// Mock 实现：不联网。alpha/dev 默认无注册联系人命中（0 匹配为合法态），
/// 真实命中走 [RemoteContactDiscoveryRepository]（beta/gamma/prod）。不在此伪造
/// 第二套业务名单（遵守 mock 数据隔离 R15）。
class MockContactDiscoveryRepository implements ContactDiscoveryRepository {
  ContactDiscoveryResultView? _latest;

  @override
  Future<ContactDiscoveryResultView> initiate(List<String> hashedPhones) async {
    await Future<void>.delayed(const Duration(milliseconds: 200));
    final result = ContactDiscoveryResultView(
      id: 'mock_cd_${DateTime.now().millisecondsSinceEpoch}',
      status: 'completed',
      matchedSubAccountIds: const <String>[],
      matchCount: 0,
      matches: const <ContactDiscoveryMatchWireDto>[],
    );
    _latest = result;
    return result;
  }

  @override
  Future<ContactDiscoveryResultView?> getLatest() async => _latest;

  @override
  Future<void> dismiss(String id) async {
    _latest = null;
  }
}

class RemoteContactDiscoveryRepository implements ContactDiscoveryRepository {
  RemoteContactDiscoveryRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _client = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  @override
  Future<ContactDiscoveryResultView> initiate(List<String> hashedPhones) async {
    final resp = await _client.postJson(
      _uri(UserApiMetadata.initiateContactDiscoveryPath),
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.initiateContactDiscovery,
      ),
      body: <String, dynamic>{'hashedPhones': hashedPhones},
    );
    return ContactDiscoveryResultView.fromMap(
      CloudResponseDecoder.asObject(
        resp,
        context: UserRequestPageIds.initiateContactDiscovery,
      ),
    );
  }

  @override
  Future<ContactDiscoveryResultView?> getLatest() async {
    try {
      final resp = await _client.getJson(
        _uri(UserApiMetadata.getLatestContactDiscoveryPath),
        headers: CloudRequestHeaders.forPage(
          UserRequestPageIds.getLatestContactDiscovery,
        ),
      );
      final obj = CloudResponseDecoder.asObject(
        resp,
        context: UserRequestPageIds.getLatestContactDiscovery,
      );
      if (obj.isEmpty || (obj['id']?.toString() ?? '').isEmpty) {
        return null;
      }
      return ContactDiscoveryResultView.fromMap(obj);
    } on CloudException catch (e) {
      // 无历史记录时服务端返回 404，语义上等价于「尚未匹配」。
      if (e.type == CloudErrorType.notFound) {
        return null;
      }
      rethrow;
    }
  }

  @override
  Future<void> dismiss(String id) async {
    await _client.deleteJson(
      _uri(UserApiMetadata.dismissContactDiscoveryPath(id: id)),
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.dismissContactDiscovery,
      ),
    );
  }
}
