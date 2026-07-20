/// Circle 域 API Contract Runner
///
/// 守护目标：Circle 聚合本体命令回执（circleId/version/status/idempotentReplay）、
/// 服务端内部 CAS 与 no-op receipt 语义、CircleMembership join/leave 生命周期
/// 在真实环境上与 local_contract 的 Mock/Facade 行为一致（R12 一体性）。
///
/// 驱动文件：
///   contracts/metadata/social/circle/tests/contract.yaml
///   contracts/metadata/social/circle_membership/tests/contract.yaml
///
/// 执行方式：
///   ```
///   flutter test test/api_integration/cloud/circle/circle_api_contract_runner.dart \
///     --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=API_CONTRACT_BASE_URL=https://gamma-api.quwoquan.com
///   ```
///
/// Runner 通过公开匿名登录取得短期 bearer；不接收外部 token。
/// gamma 不可用或未配置 → 直接 fail（诚实语义，不静默跳过）。
///
/// Mock Wall：本文件发真实 HTTP，位于 Mock Wall 右侧，禁止注入 MockRepository。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import '../../../support/api_contract/local_bad_certificate_overrides.dart';
import '../../../support/api_contract/local_gamma_anonymous_session.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _allowBadCertificateForLocalApiContract = bool.fromEnvironment(
  'API_CONTRACT_ALLOW_BAD_CERT',
);

bool _apiAvailable = false;
late http.Client _client;
late LocalGammaAnonymousSession _session;

Map<String, String> _headers(String idempotencyKey) => <String, String>{
  'Content-Type': 'application/json',
  'Authorization': _session.authorizationHeader,
  if (idempotencyKey.isNotEmpty) 'Idempotency-Key': idempotencyKey,
};

Future<http.Response> _post(
  String path,
  Map<String, Object?> body, {
  required String idempotencyKey,
}) => _client
    .post(
      Uri.parse('$_apiBase$path'),
      headers: _headers(idempotencyKey),
      body: jsonEncode(body),
    )
    .timeout(const Duration(seconds: 10));

Future<http.Response> _patch(
  String path,
  Map<String, Object?> body, {
  required String idempotencyKey,
}) => _client
    .patch(
      Uri.parse('$_apiBase$path'),
      headers: _headers(idempotencyKey),
      body: jsonEncode(body),
    )
    .timeout(const Duration(seconds: 10));

Future<http.Response> _delete(
  String path, {
  required String idempotencyKey,
}) => _client
    .delete(Uri.parse('$_apiBase$path'), headers: _headers(idempotencyKey))
    .timeout(const Duration(seconds: 10));

Map<String, dynamic> _json(http.Response response) =>
    jsonDecode(response.body) as Map<String, dynamic>;

void main() {
  setUpAll(() async {
    installLocalApiContractBadCertificateOverride(
      enabled: _allowBadCertificateForLocalApiContract,
    );
    if (_apiBase.isEmpty) {
      throw StateError('L3: ${_apiContractEnv.toUpperCase()}_BASE_URL not set');
    }
    try {
      final probe = await http
          .get(Uri.parse('$_apiBase/healthz'))
          .timeout(const Duration(seconds: 5));
      if (probe.statusCode >= 500) {
        throw StateError('L3: $_apiContractEnv returned ${probe.statusCode}');
      }
    } catch (e) {
      throw StateError('L3: $_apiContractEnv unreachable ($e)');
    }
    _client = http.Client();
    _session = await LocalGammaAnonymousSession.login(
      client: _client,
      baseUrl: _apiBase,
      subject: 'circle-api-contract-v1',
    );
    _apiAvailable = true;
  });

  tearDownAll(() {
    if (_apiAvailable) _client.close();
    restoreLocalApiContractBadCertificateOverride();
  });

  // ── 场景 1：circle 本体 CRUD 生命周期 + 幂等回执 + no-op receipt ─────────
  // contract.yaml: circle_create_with_owner / circle_update_owner_cas /
  //                circle_archive_named_transition
  group('circle_lifecycle_end_to_end', () {
    late String circleId;
    final createKey = 'l3-circle-create-${DateTime.now().microsecondsSinceEpoch}';

    test('CreateCircle 返回稳定回执且同 key 重放', () async {
      if (!_apiAvailable) return markTestSkipped('$_apiContractEnv unavailable');
      final body = <String, Object?>{
        'name': 'L3 契约圈 $createKey',
        'category': 'tech',
        'tags': ['l3-contract'],
      };
      final created = await _post('/circles', body, idempotencyKey: createKey);
      expect(created.statusCode, 201, reason: created.body);
      final receipt = _json(created);
      expect(
        receipt.keys.toSet(),
        {'circleId', 'version', 'status', 'idempotentReplay'},
        reason: '命令回执必须是稳定形状（无多余键）',
      );
      circleId = receipt['circleId'] as String;
      expect(circleId, isNotEmpty);
      expect(receipt['version'], 1);
      expect(receipt['status'], 'active');
      expect(receipt['idempotentReplay'], false);

      final replayed = await _post('/circles', body, idempotencyKey: createKey);
      expect(replayed.statusCode, 201, reason: replayed.body);
      final replayReceipt = _json(replayed);
      expect(replayReceipt['circleId'], circleId);
      expect(replayReceipt['idempotentReplay'], true);
    });

    test('UpdateCircle 服务端 CAS 推进版本且详情回读一致', () async {
      if (!_apiAvailable) return markTestSkipped('$_apiContractEnv unavailable');
      final updated = await _patch(
        '/circles/$circleId',
        {'description': 'L3 更新描述'},
        idempotencyKey: 'l3-circle-update-$circleId',
      );
      expect(updated.statusCode, 200, reason: updated.body);
      final receipt = _json(updated);
      expect(receipt['version'], 2);
      expect(receipt['status'], 'active');

      final detail = await _client
          .get(
            Uri.parse('$_apiBase/circles/$circleId'),
            headers: {'Authorization': _session.authorizationHeader},
          )
          .timeout(const Duration(seconds: 10));
      expect(detail.statusCode, 200, reason: detail.body);
      final data = _json(detail)['data'] as Map<String, dynamic>;
      expect(data['description'], 'L3 更新描述');
      expect(data['version'], 2, reason: '详情回读必须暴露聚合版本');
    });

    test('ArchiveCircle 命名迁移；已归档时 no-op receipt 不递增版本', () async {
      if (!_apiAvailable) return markTestSkipped('$_apiContractEnv unavailable');
      final archived = await _delete(
        '/circles/$circleId',
        idempotencyKey: 'l3-circle-archive-$circleId',
      );
      expect(archived.statusCode, 200, reason: archived.body);
      final receipt = _json(archived);
      expect(receipt['status'], 'archived');
      expect(receipt['version'], 3);

      final noop = await _delete(
        '/circles/$circleId',
        idempotencyKey: 'l3-circle-archive-noop-$circleId',
      );
      expect(noop.statusCode, 200, reason: noop.body);
      final noopReceipt = _json(noop);
      expect(noopReceipt['version'], 3, reason: 'no-op 不得递增版本');
      expect(noopReceipt['idempotentReplay'], true);

      final noopReplay = await _delete(
        '/circles/$circleId',
        idempotencyKey: 'l3-circle-archive-noop-$circleId',
      );
      expect(noopReplay.statusCode, 200, reason: noopReplay.body);
      expect(_json(noopReplay)['idempotentReplay'], true);
    });
  });

  // ── 场景 2：membership join/leave 生命周期 ────────────────────────────────
  // contract.yaml: membership_transaction_replay_projection_stream
  group('circle_membership_join_leave_end_to_end', () {
    late String circleId;

    setUpAll(() async {
      if (!_apiAvailable) return;
      final created = await _post(
        '/circles',
        {
          'name': 'L3 成员圈 ${DateTime.now().microsecondsSinceEpoch}',
          'category': 'interest',
        },
        idempotencyKey:
            'l3-membership-circle-${DateTime.now().microsecondsSinceEpoch}',
      );
      if (created.statusCode != 201) {
        throw StateError('seed membership circle failed: ${created.body}');
      }
      circleId = _json(created)['circleId'] as String;
    });

    test('JoinCircle / LeaveCircle 回执与重放语义', () async {
      if (!_apiAvailable) return markTestSkipped('$_apiContractEnv unavailable');
      final joinKey = 'l3-join-$circleId';
      final joined = await _post(
        '/circles/$circleId/memberships',
        const <String, Object?>{},
        idempotencyKey: joinKey,
      );
      // 圈主由 CreateCircle 建立所有权；匿名会话对自己创建的圈子 join 属
      // membership_already_active 或正常 join，两者都必须是稳定契约结果。
      expect(joined.statusCode, anyOf(201, 200, 409), reason: joined.body);
      if (joined.statusCode == 409) {
        expect(_json(joined)['code'], 'CIRCLE.USER.membership_already_active');
        return;
      }
      final joinReceipt = _json(joined);
      expect(joinReceipt['membershipId'], isNotEmpty);
      expect(joinReceipt['state'], 'active');
      expect(joinReceipt['idempotentReplay'], false);

      final joinReplay = await _post(
        '/circles/$circleId/memberships',
        const <String, Object?>{},
        idempotencyKey: joinKey,
      );
      expect(_json(joinReplay)['idempotentReplay'], true);

      final left = await _delete(
        '/circles/$circleId/memberships/self',
        idempotencyKey: 'l3-leave-$circleId',
      );
      expect(left.statusCode, 200, reason: left.body);
      expect(_json(left)['state'], 'left');
    });
  });
}
