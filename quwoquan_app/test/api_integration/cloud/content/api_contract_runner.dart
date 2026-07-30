/// L3 API Contract Runner
///
/// **请求/响应断言**：优先用 codegen `dto.toMap()` 再 `Map<String, Object?>.from(...)` 对齐形状；HTTP 响应仍 `json.decode` 后做 wire 校验（session_c §6）。
///
/// 守护目标：端云数据合约不漂移（cursor 分页语义、错误码格式、字段可见性、响应时间 SLO）
/// 用例身份由 acceptance 稳定 case ID 绑定，测试路径由 runner 扫描生成。
///
/// 执行方式：
///   ```
///   API_CONTRACT_ENV=gamma \
///   GAMMA_BASE_URL=https://api.gamma.quwoquan.com \
///   GAMMA_PRODUCT_OPS_BASE_URL=https://ops.gamma.quwoquan.com \
///   make test-api-contract
///
///   # 或直接执行本文件：
///   flutter test test/api_integration/cloud/content/api_contract_runner.dart \
///     --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=API_CONTRACT_BASE_URL=...
///   ```
///
/// Runner 通过公开匿名登录取得短期 bearer；不接收外部 token，也不注入用户身份头。
///
/// CI 策略：
///   - daily（gamma 必须可用）
///   - pre-release 必须通过
///   - gamma 不可用或未配置 → 直接 fail
///
/// Mock Wall：本文件发真实 HTTP，位于 Mock Wall 右侧，禁止注入 MockRepository。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_read_model_projection.dart';

import '../../../support/api_contract/local_gamma_anonymous_session.dart';

// dart-define 注入；本地执行时通过 make test-api-contract 传入。
const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _localGammaT3Scope = String.fromEnvironment('LOCAL_GAMMA_T3_SCOPE');

// ─── Shared client ─────────────────────────────────────────────────────────

// _apiAvailable guards all tests after a skip decision in setUpAll.
// When markTestSkipped is called, subsequent tests still attempt to run;
// checking this flag prevents LateInitializationError on _client.
bool _apiAvailable = false;
late http.Client _client;
late LocalGammaAnonymousSession _session;
int _idempotencySequence = 0;

Map<String, String> _authHeaders(String pageId) => <String, String>{
  ..._client.headers ?? {},
  ...CloudRequestHeaders.forPage(pageId),
  'Authorization': _session.authorizationHeader,
};

String _nextIdempotencyKey(String operation) {
  _idempotencySequence += 1;
  return '$operation-${DateTime.now().toUtc().microsecondsSinceEpoch}-$_idempotencySequence';
}

Map<String, String> _commandHeaders(
  String pageId, {
  required String idempotencyKey,
}) => <String, String>{
  ..._authHeaders(pageId),
  'Idempotency-Key': idempotencyKey,
};

bool get _isLocalGammaContentOnly =>
    _apiContractEnv == 'gamma' && _localGammaT3Scope == 'content';

Map<String, Object> _behaviorEvent(
  String action, {
  required String clientEventId,
  String? state,
  double? duration,
  int? position,
}) => <String, Object>{
  'clientEventId': clientEventId,
  'occurredAt': DateTime.now().toUtc().toIso8601String(),
  'contentId': 'fixture_photo_001',
  'action': action,
  'contentType': 'image',
  ...?switch (state) {
    final value? => <String, Object>{'state': value},
    null => null,
  },
  ...?switch (duration) {
    final value? => <String, Object>{'duration': value},
    null => null,
  },
  ...?switch (position) {
    final value? => <String, Object>{'position': value},
    null => null,
  },
};

// ─── Tests ─────────────────────────────────────────────────────────────────

void main() {
  // ── 环境可达性探测：不可达则直接 fail ───────────────────────────────
  setUpAll(() async {
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
      subject: 'content-api-contract',
    );
    _apiAvailable = true;
  });

  tearDownAll(() {
    if (_apiAvailable) _client.close();
  });

  // ── 场景 1：feed_cursor_pagination_end_to_end ──────────────────────────────
  // e2e.yaml: feed_cursor_pagination_end_to_end [test_type: api_contract]
  group('feed_cursor_pagination_end_to_end', () {
    test('第一页返回 20 条 + cursor 非空', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      final url = Uri.parse('$_apiBase/content/feed?type=image&limit=20');
      final sw = Stopwatch()..start();
      final resp = await _client
          .get(url, headers: _authHeaders('content.feed'))
          .timeout(const Duration(seconds: 10));
      sw.stop();

      // 协议层
      expect(resp.statusCode, 200, reason: 'feed API should return 200');
      expect(
        sw.elapsedMilliseconds,
        lessThan(800),
        reason: 'feed API SLO: <800ms on $_apiContractEnv',
      );

      // 结构层
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(body.containsKey('items'), isTrue);
      expect(body.containsKey('cursor'), isTrue);

      final items = (body['items'] as List)
          .map((e) => contentPostDtoFromReadModelMap(e as Map<String, dynamic>))
          .toList();
      expect(items, isNotEmpty);

      final cursor = body['cursor'] as String?;
      expect(
        cursor,
        isNotNull,
        reason: 'cursor must be present for pagination',
      );
      expect(cursor, isNotEmpty);
    });

    test('第二页与第一页无重叠 item', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      final page1Url = Uri.parse('$_apiBase/content/feed?type=image&limit=20');
      final resp1 = await _client
          .get(page1Url, headers: _authHeaders('content.feed'))
          .timeout(const Duration(seconds: 10));
      expect(resp1.statusCode, 200);

      final body1 = jsonDecode(resp1.body) as Map<String, dynamic>;
      final cursor = body1['cursor'] as String;
      final ids1 = (body1['items'] as List)
          .map((e) => (e as Map<String, dynamic>)['postId'] as String)
          .toSet();

      final page2Url = Uri.parse(
        '$_apiBase/content/feed?type=image&limit=20&cursor=$cursor',
      );
      final resp2 = await _client
          .get(page2Url, headers: _authHeaders('content.feed'))
          .timeout(const Duration(seconds: 10));
      expect(resp2.statusCode, 200);

      final ids2 = ((jsonDecode(resp2.body) as Map)['items'] as List)
          .map((e) => (e as Map<String, dynamic>)['postId'] as String)
          .toSet();

      // 语义层：两页无交集
      expect(
        ids1.intersection(ids2),
        isEmpty,
        reason: 'no item overlap between page 1 and page 2',
      );
    });

    test('服务 read model 投影为 PhotoPostDto 且包含 aspectRatio', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      final url = Uri.parse('$_apiBase/content/feed?type=image&limit=5');
      final resp = await _client
          .get(url, headers: _authHeaders('content.feed'))
          .timeout(const Duration(seconds: 10));
      expect(resp.statusCode, 200);

      final items = (jsonDecode(resp.body)['items'] as List)
          .map((e) => contentPostDtoFromReadModelMap(e as Map<String, dynamic>))
          .whereType<PhotoPostDto>()
          .toList();

      for (final item in items) {
        final hasDimensions =
            item.width != null && item.height != null && item.height! > 0;
        if (hasDimensions) {
          expect(
            item.aspectRatio,
            isNotNull,
            reason: 'aspectRatio must be computable when width/height exist',
          );
          expect(
            item.aspectRatio,
            greaterThan(0),
            reason: 'aspectRatio must be positive when dimensions exist',
          );
        } else {
          expect(
            item.aspectRatio,
            isNull,
            reason: 'aspectRatio must stay null when dimensions are absent',
          );
        }
      }
    });

    test('视频书查询返回可播放的 VideoPostDto', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      final url = Uri.parse(
        '$_apiBase/content/feed'
        '?identity=work&type=video&sort=recommend&limit=20',
      );
      final resp = await _client
          .get(url, headers: _authHeaders('content.feed.video'))
          .timeout(const Duration(seconds: 10));

      expect(resp.statusCode, 200);
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      final items = (body['items'] as List)
          .map(
            (item) =>
                contentPostDtoFromReadModelMap(item as Map<String, dynamic>),
          )
          .toList(growable: false);
      expect(items, isNotEmpty, reason: 'video book feed must not be empty');
      expect(items, everyElement(isA<VideoPostDto>()));
      for (final item in items.whereType<VideoPostDto>()) {
        expect(item.identity, 'work');
        expect(item.type, 'video');
        expect(item.videoUrl, isNotEmpty);
      }
    });
  });

  // ── 场景 2：behavior_batch_report_reaches_service ─────────────────────────
  // e2e.yaml: behavior_batch_report_reaches_service [test_type: api_contract]
  group('behavior_batch_report_reaches_service', () {
    test('POST /content/behaviors 返回 204', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      final url = Uri.parse('$_apiBase/content/behaviors');
      final sw = Stopwatch()..start();
      final idempotencyKey = _nextIdempotencyKey('content-behavior-batch');
      final resp = await _client
          .post(
            url,
            headers: {
              ..._commandHeaders(
                'content.behavior',
                idempotencyKey: idempotencyKey,
              ),
              'Content-Type': 'application/json',
            },
            body: jsonEncode({
              'events': [
                _behaviorEvent(
                  'impression',
                  clientEventId: '$idempotencyKey-impression',
                  state: 'impressed',
                  position: 0,
                ),
                _behaviorEvent(
                  'dwell',
                  clientEventId: '$idempotencyKey-dwell',
                  duration: 12,
                ),
              ],
            }),
          )
          .timeout(const Duration(seconds: 10));
      sw.stop();

      // 协议层
      expect(
        resp.statusCode,
        204,
        reason: 'behavior batch should return 204 No Content',
      );
      expect(
        sw.elapsedMilliseconds,
        lessThan(500),
        reason: 'behavior API SLO: <500ms on $_apiContractEnv',
      );
    });

    test('事件 action 字段与 behaviors.yaml 枚举对齐', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      // 验证合法 action 值（来自 behaviors.yaml behavior_events）被接受。
      final validActions = ['impression', 'dwell', 'click', 'share'];
      for (final action in validActions) {
        final idempotencyKey = _nextIdempotencyKey('content-behavior-$action');
        final resp = await _client
            .post(
              Uri.parse('$_apiBase/content/behaviors'),
              headers: {
                ..._commandHeaders(
                  'content.behavior',
                  idempotencyKey: idempotencyKey,
                ),
                'Content-Type': 'application/json',
              },
              body: jsonEncode({
                'events': [
                  _behaviorEvent(
                    action,
                    clientEventId: '$idempotencyKey-event',
                    state: action == 'impression' ? 'impressed' : null,
                    duration: action == 'dwell' ? 12 : null,
                  ),
                ],
              }),
            )
            .timeout(const Duration(seconds: 10));
        expect(
          resp.statusCode,
          204,
          reason: 'behavior action "$action" should be accepted (204)',
        );
      }
    });

    // e2e.yaml assertion: "like event NOT present in batch（专属路由）"
    // The batch /behaviors endpoint should reject 'like' events (dedicated POST /posts/{id}/like).
    test('like action 被 batch 端点拒绝（专属路由）', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      final idempotencyKey = _nextIdempotencyKey('content-behavior-like');
      final resp = await _client
          .post(
            Uri.parse('$_apiBase/content/behaviors'),
            headers: {
              ..._commandHeaders(
                'content.behavior',
                idempotencyKey: idempotencyKey,
              ),
              'Content-Type': 'application/json',
            },
            body: jsonEncode({
              'events': [
                _behaviorEvent('like', clientEventId: '$idempotencyKey-event'),
              ],
            }),
          )
          .timeout(const Duration(seconds: 10));
      // 服务端应返回 400（非法事件类型），而非 204
      expect(
        resp.statusCode,
        400,
        reason:
            '"like" is a dedicated route and must be rejected by batch endpoint',
      );
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(
        body.containsKey('code'),
        isTrue,
        reason: 'error response must have code field',
      );
    });
  });

  // ── 场景 3：error_state_displayed_correctly ───────────────────────────────
  // e2e.yaml: error_state_displayed_correctly [test_type: api_contract]
  group('error_state_displayed_correctly', () {
    test('不存在的 postId → 404 + CONTENT.USER.post_not_found', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      final resp = await _client
          .get(
            Uri.parse('$_apiBase/content/posts/nonexistent_00000000'),
            headers: _authHeaders('content.post'),
          )
          .timeout(const Duration(seconds: 10));

      // 协议层
      expect(resp.statusCode, 404);

      // 结构层
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(
        body['code'],
        'CONTENT.USER.post_not_found',
        reason: 'error code must match errors.yaml',
      );
      // 语义层：端侧 ErrorCode 映射正确
      final exception = CloudErrorMapper.fromStatusCode(
        resp.statusCode,
        body: resp.body,
        requestPath: '/content/posts/nonexistent',
      );
      expect(exception.domainErrorCode?.value, ContentErrorCode.postNotFound);
      expect(
        ContentErrorMessages.zh[exception.domainErrorCode?.value],
        '内容不存在或已删除',
      );
    });
  });

  // ── 场景 4：media_not_ready_graceful_error ────────────────────────────────
  // e2e.yaml: media_not_ready_graceful_error [test_type: api_contract]
  group('media_not_ready_graceful_error', () {
    test(
      'X-Test-Error-Inject 触发 metadata media_not_ready → 400 + retry/3s',
      () async {
        if (!_apiAvailable) {
          return markTestSkipped('$_apiContractEnv unavailable');
        }
        final idempotencyKey = _nextIdempotencyKey('content-media-not-ready');
        // 此 header 仅在非生产 profile 开启，生产不生效。
        final resp = await _client
            .post(
              Uri.parse('$_apiBase/content/posts:publish'),
              headers: {
                ..._commandHeaders(
                  'content.post.publish',
                  idempotencyKey: idempotencyKey,
                ),
                'Content-Type': 'application/json',
                'X-Test-Error-Inject': 'CONTENT.USER.media_not_ready',
              },
              body: jsonEncode({
                'publishIntentId': idempotencyKey,
                'localDraftId': 'draft-$idempotencyKey',
                'contentType': 'image',
                'mediaAssetIds': ['fixture_media_not_ready'],
              }),
            )
            .timeout(const Duration(seconds: 10));

        // 协议层
        expect(resp.statusCode, ContentErrorCode.mediaNotReady.httpStatus);

        // 结构层
        final body = jsonDecode(resp.body) as Map<String, dynamic>;
        expect(body['code'], 'CONTENT.USER.media_not_ready');
        // 语义层：端侧消息正确
        final code = ContentErrorCode.fromCode(body['code'] as String);
        expect(code, ContentErrorCode.mediaNotReady);
        expect(ContentErrorMessages.zh[code], '媒体文件正在处理中，请稍后发布');
        expect(code.recoveryAction, 'retry');
        expect(code.recoveryAfterSeconds, 3);
      },
    );
  });

  // ── 场景 5：dedicated_feedback_and_user_block_contract ────────────────────
  group('dedicated_feedback_and_user_block_contract', () {
    const postId = 'fixture_photo_001';

    test('POST /content/reports 可用', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      final resp = await _client
          .post(
            Uri.parse('$_apiBase/content/reports'),
            headers: {
              ..._authHeaders('content.report.create'),
              'Content-Type': 'application/json',
              'Idempotency-Key':
                  'report-${DateTime.now().microsecondsSinceEpoch}',
            },
            body: jsonEncode({
              'targetId': postId,
              'targetType': 'post',
              'reason': 'spam',
              'description': 'api contract',
            }),
          )
          .timeout(const Duration(seconds: 10));
      expect(resp.statusCode, 204);
    });

    test('POST/DELETE /user/personas/{targetPersonaId}/block 可用', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      if (_isLocalGammaContentOnly) {
        return markTestSkipped(
          'local gamma content mirror excludes user routes',
        );
      }
      const targetUserId = 'contract_block_target_001';
      final blockResp = await _client
          .post(
            Uri.parse('$_apiBase/user/personas/$targetUserId/block'),
            headers: _authHeaders('user.block.create'),
          )
          .timeout(const Duration(seconds: 10));
      expect(
        [200, 201, 204].contains(blockResp.statusCode),
        isTrue,
        reason: 'block user route should succeed',
      );

      final unblockResp = await _client
          .delete(
            Uri.parse('$_apiBase/user/personas/$targetUserId/block'),
            headers: _authHeaders('user.block.delete'),
          )
          .timeout(const Duration(seconds: 10));
      expect(
        [200, 204].contains(unblockResp.statusCode),
        isTrue,
        reason: 'unblock user route should succeed',
      );
    });

    test('PATCH /user/settings/privacy 可写并回读 blockedKeywords', () async {
      if (!_apiAvailable) {
        return markTestSkipped('$_apiContractEnv unavailable');
      }
      if (_isLocalGammaContentOnly) {
        return markTestSkipped(
          'local gamma content mirror excludes user routes',
        );
      }
      final patchResp = await _client
          .patch(
            Uri.parse('$_apiBase/user/settings/privacy'),
            headers: {
              ..._authHeaders('user.settings.privacy.patch'),
              'Content-Type': 'application/json',
            },
            body: jsonEncode({
              'blockedKeywords': ['api_contract_kw'],
            }),
          )
          .timeout(const Duration(seconds: 10));
      expect(
        [200, 204].contains(patchResp.statusCode),
        isTrue,
        reason: 'privacy patch should accept blockedKeywords',
      );

      final getResp = await _client
          .get(
            Uri.parse('$_apiBase/user/settings/privacy'),
            headers: _authHeaders('user.settings.privacy.get'),
          )
          .timeout(const Duration(seconds: 10));
      expect(getResp.statusCode, 200);
      final body = jsonDecode(getResp.body) as Map<String, dynamic>;
      expect(
        body['blockedKeywords'],
        contains('api_contract_kw'),
        reason: 'blockedKeywords should round-trip through privacy settings',
      );
    });
  });
}

// ─── Extension：http.Client headers 兼容 ─────────────────────────────────
extension on http.Client {
  // http.Client 不暴露 headers 属性；用空 Map 填充，
  // 实际 headers 在 _authHeaders() 里由 CloudRequestHeaders.forPage 生成。
  Map<String, String>? get headers => null;
}
