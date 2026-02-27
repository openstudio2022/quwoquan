/// L3 API Contract Runner
///
/// 守护目标：端云数据合约不漂移（cursor 分页语义、错误码格式、字段可见性、响应时间 SLO）
/// 驱动文件：contracts/metadata/content/post/tests/e2e.yaml [test_type: api_contract]
///
/// 执行方式：
///   ```
///   STAGING_BASE_URL=https://staging.api.quwoquan.com \
///   TEST_AUTH_TOKEN=TOKEN \
///   flutter test test/cloud/content/api_contract_runner.dart \
///     --dart-define=STAGING_BASE_URL=... \
///     --dart-define=TEST_AUTH_TOKEN=...
///   ```
///
/// CI 策略：
///   - daily（staging 可用时自动触发）
///   - pre-release 必须通过
///   - staging 不可用 → markTestSkipped，不 fail
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

// dart-define 注入；本地执行时通过 make test-api-contract 传入。
const _stagingBase = String.fromEnvironment('STAGING_BASE_URL');
const _testToken = String.fromEnvironment('TEST_AUTH_TOKEN');

// ─── Shared client & seeded data ───────────────────────────────────────────

// _stagingAvailable guards all tests after a skip decision in setUpAll.
// When markTestSkipped is called, subsequent tests still attempt to run;
// checking this flag prevents LateInitializationError on _client.
bool _stagingAvailable = false;
late http.Client _client;

/// 在 staging 上创建一条 image post，返回新建 postId。
Future<String> _seedPhotoPost() async {
  final url = Uri.parse('$_stagingBase/v1/content/posts');
  final resp = await _client
      .post(
        url,
        headers: {
          ..._authHeaders('content.post.create'),
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'contentType': 'image',
          'title': 'L3 contract seed post',
          'body': 'automated test fixture — safe to delete',
          'mediaUrls': ['https://example.com/test.jpg'],
          'width': 1200,
          'height': 800,
        }),
      )
      .timeout(const Duration(seconds: 10));
  if (resp.statusCode != 201) {
    throw Exception('_seedPhotoPost failed: ${resp.statusCode} ${resp.body}');
  }
  final id = (jsonDecode(resp.body) as Map<String, dynamic>)['_id'] as String;
  return id;
}

/// 删除 staging 上由本次测试创建的 post。
Future<void> _deletePost(String postId) async {
  final url = Uri.parse('$_stagingBase/v1/content/posts/$postId');
  await _client
      .delete(url, headers: _authHeaders('content.post.delete'))
      .timeout(const Duration(seconds: 10));
  // 404 可接受（已被其他测试删除或自动清理）
}

Map<String, String> _authHeaders(String pageId) => {
      ..._client.headers ?? {},
      ...CloudRequestHeaders.forPage(pageId),
      if (_testToken.isNotEmpty) 'Authorization': 'Bearer $_testToken',
    };

// ─── Tests ─────────────────────────────────────────────────────────────────

void main() {
  // ── Staging 可达性探测：不可达则 skip 全部场景 ────────────────────────────
  setUpAll(() async {
    if (_stagingBase.isEmpty) {
      markTestSkipped('L3: STAGING_BASE_URL not set — all api_contract tests skipped');
      return;
    }
    try {
      final probe = await http
          .head(Uri.parse(_stagingBase))
          .timeout(const Duration(seconds: 5));
      if (probe.statusCode >= 500) {
        markTestSkipped(
            'L3: staging returned ${probe.statusCode} — tests skipped');
        return;
      }
    } catch (e) {
      markTestSkipped('L3: staging unreachable ($e) — tests skipped');
      return;
    }
    _client = http.Client();
    _stagingAvailable = true;
  });

  tearDownAll(() {
    if (_stagingAvailable) _client.close();
  });

  // ── 场景 1：feed_cursor_pagination_end_to_end ──────────────────────────────
  // e2e.yaml: feed_cursor_pagination_end_to_end [test_type: api_contract]
  group('feed_cursor_pagination_end_to_end', () {
    late List<String> seededIds;

    setUpAll(() async {
      if (!_stagingAvailable) return;
      seededIds = await Future.wait(
        List.generate(25, (_) => _seedPhotoPost()),
      );
    });

    tearDownAll(() async {
      if (!_stagingAvailable) return;
      await Future.wait(seededIds.map(_deletePost));
    });

    test('第一页返回 20 条 + cursor 非空', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final url =
          Uri.parse('$_stagingBase/v1/content/feed?type=image&limit=20');
      final sw = Stopwatch()..start();
      final resp = await _client
          .get(url, headers: _authHeaders('content.feed'))
          .timeout(const Duration(seconds: 10));
      sw.stop();

      // 协议层
      expect(resp.statusCode, 200, reason: 'feed API should return 200');
      expect(sw.elapsedMilliseconds, lessThan(800),
          reason: 'feed API SLO: <800ms on staging');

      // 结构层
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(body.containsKey('items'), isTrue);
      expect(body.containsKey('cursor'), isTrue);

      final items = (body['items'] as List)
          .map((e) => postBaseDtoFromMap(e as Map<String, dynamic>))
          .toList();
      expect(items, isNotEmpty);

      final cursor = body['cursor'] as String?;
      expect(cursor, isNotNull, reason: 'cursor must be present for pagination');
      expect(cursor, isNotEmpty);
    });

    test('第二页与第一页无重叠 item', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final page1Url =
          Uri.parse('$_stagingBase/v1/content/feed?type=image&limit=20');
      final resp1 = await _client
          .get(page1Url, headers: _authHeaders('content.feed'))
          .timeout(const Duration(seconds: 10));
      expect(resp1.statusCode, 200);

      final body1 = jsonDecode(resp1.body) as Map<String, dynamic>;
      final cursor = body1['cursor'] as String;
      final ids1 = (body1['items'] as List)
          .map((e) => (e as Map<String, dynamic>)['_id'] as String)
          .toSet();

      final page2Url = Uri.parse(
          '$_stagingBase/v1/content/feed?type=image&limit=20&cursor=$cursor');
      final resp2 = await _client
          .get(page2Url, headers: _authHeaders('content.feed'))
          .timeout(const Duration(seconds: 10));
      expect(resp2.statusCode, 200);

      final ids2 = ((jsonDecode(resp2.body) as Map)['items'] as List)
          .map((e) => (e as Map<String, dynamic>)['_id'] as String)
          .toSet();

      // 语义层：两页无交集
      expect(ids1.intersection(ids2), isEmpty,
          reason: 'no item overlap between page 1 and page 2');
    });

    test('PhotoPostDto fromMap 解析所有字段包含 aspectRatio', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final url =
          Uri.parse('$_stagingBase/v1/content/feed?type=image&limit=5');
      final resp = await _client
          .get(url, headers: _authHeaders('content.feed'))
          .timeout(const Duration(seconds: 10));
      expect(resp.statusCode, 200);

      final items = (jsonDecode(resp.body)['items'] as List)
          .map((e) => postBaseDtoFromMap(e as Map<String, dynamic>))
          .whereType<PhotoPostDto>()
          .toList();

      for (final item in items) {
        expect(item.aspectRatio, isNotNull,
            reason: 'PhotoPostDto.aspectRatio must be computable');
        expect(item.aspectRatio, greaterThan(0),
            reason: 'aspectRatio must be positive');
      }
    });
  });

  // ── 场景 2：behavior_batch_report_reaches_service ─────────────────────────
  // e2e.yaml: behavior_batch_report_reaches_service [test_type: api_contract]
  group('behavior_batch_report_reaches_service', () {
    late String postId;

    setUpAll(() async {
      if (!_stagingAvailable) return;
      postId = await _seedPhotoPost();
    });

    tearDownAll(() async {
      if (!_stagingAvailable) return;
      await _deletePost(postId);
    });

    test('POST /v1/content/behaviors 返回 204', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final url = Uri.parse('$_stagingBase/v1/content/behaviors');
      final sw = Stopwatch()..start();
      final resp = await _client
          .post(
            url,
            headers: {
              ..._authHeaders('content.behavior'),
              'Content-Type': 'application/json',
            },
            body: jsonEncode({
              'events': [
                {
                  'postId': postId,
                  'type': 'impression',
                  'feedPosition': 0,
                },
                {
                  'postId': postId,
                  'type': 'dwell',
                  'dwellMs': 12000,
                },
              ],
            }),
          )
          .timeout(const Duration(seconds: 10));
      sw.stop();

      // 协议层
      expect(resp.statusCode, 204,
          reason: 'behavior batch should return 204 No Content');
      expect(sw.elapsedMilliseconds, lessThan(500),
          reason: 'behavior API SLO: <500ms on staging');
    });

    test('事件 type 字段与 behaviors.yaml 枚举对齐', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      // 验证合法 type 值（来自 behaviors.yaml behavior_events）被接受（不返回 400）
      final validTypes = ['impression', 'dwell', 'click', 'share', 'favorite'];
      for (final type in validTypes) {
        final resp = await _client
            .post(
              Uri.parse('$_stagingBase/v1/content/behaviors'),
              headers: {
                ..._authHeaders('content.behavior'),
                'Content-Type': 'application/json',
              },
              body: jsonEncode({
                'events': [
                  {'postId': postId, 'type': type},
                ],
              }),
            )
            .timeout(const Duration(seconds: 10));
        expect(resp.statusCode, 204,
            reason: 'behavior type "$type" should be accepted (204)');
      }
    });

    // e2e.yaml assertion: "like event NOT present in batch (dedicated route)"
    // The batch /behaviors endpoint should reject 'like' events (dedicated POST /posts/{id}/like).
    test('like type 被 batch 端点拒绝（专属路由）', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final resp = await _client
          .post(
            Uri.parse('$_stagingBase/v1/content/behaviors'),
            headers: {
              ..._authHeaders('content.behavior'),
              'Content-Type': 'application/json',
            },
            body: jsonEncode({
              'events': [
                {'postId': postId, 'type': 'like'},
              ],
            }),
          )
          .timeout(const Duration(seconds: 10));
      // 服务端应返回 400（非法事件类型），而非 204
      expect(resp.statusCode, 400,
          reason: '"like" is a dedicated route and must be rejected by batch endpoint');
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(body.containsKey('code'), isTrue,
          reason: 'error response must have code field');
    });
  });

  // ── 场景 3：error_state_displayed_correctly ───────────────────────────────
  // e2e.yaml: error_state_displayed_correctly [test_type: api_contract]
  group('error_state_displayed_correctly', () {
    test('不存在的 postId → 404 + CONTENT.USER.post_not_found', () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      final resp = await _client
          .get(
            Uri.parse('$_stagingBase/v1/content/posts/nonexistent_00000000'),
            headers: _authHeaders('content.post'),
          )
          .timeout(const Duration(seconds: 10));

      // 协议层
      expect(resp.statusCode, 404);

      // 结构层
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(body['code'], 'CONTENT.USER.post_not_found',
          reason: 'error code must match errors.yaml');
      expect(body['isRetryable'], false,
          reason: 'post_not_found is not retryable per errors.yaml');

      // 语义层：端侧 ErrorCode 映射正确
      final exception = CloudErrorMapper.fromStatusCode(
        resp.statusCode,
        body: resp.body,
        requestPath: '/v1/content/posts/nonexistent',
      );
      expect(exception.errorCode, ContentErrorCode.postNotFound);
      expect(ContentErrorMessages.zh[exception.errorCode!],
          '内容不存在或已删除');
    });
  });

  // ── 场景 4：media_not_ready_graceful_error ────────────────────────────────
  // e2e.yaml: media_not_ready_graceful_error [test_type: api_contract]
  group('media_not_ready_graceful_error', () {
    test('X-Test-Error-Inject 触发 media_not_ready → 422 + isRetryable=true',
        () async {
      if (!_stagingAvailable) return markTestSkipped('staging unavailable');
      // 此 header 仅在 staging profile 开启，生产不生效
      final resp = await _client
          .post(
            Uri.parse('$_stagingBase/v1/content/posts'),
            headers: {
              ..._authHeaders('content.post.create'),
              'Content-Type': 'application/json',
              'X-Test-Error-Inject': 'CONTENT.USER.media_not_ready',
            },
            body: jsonEncode({
              'contentType': 'image',
              'mediaUrls': ['https://example.com/processing.jpg'],
            }),
          )
          .timeout(const Duration(seconds: 10));

      // 协议层
      expect(resp.statusCode, 422);

      // 结构层
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      expect(body['code'], 'CONTENT.USER.media_not_ready');
      expect(body['isRetryable'], true,
          reason: 'media_not_ready is retryable per errors.yaml');

      // 语义层：端侧消息正确
      final code = ContentErrorCode.fromCode(body['code'] as String);
      expect(code, ContentErrorCode.mediaNotReady);
      expect(ContentErrorMessages.zh[code], '媒体文件正在处理中，请稍后发布');
    });
  });
}

// ─── Extension：http.Client headers 兼容 ─────────────────────────────────
extension on http.Client {
  // http.Client 不暴露 headers 属性；用空 Map 填充，
  // 实际 headers 在 _authHeaders() 里由 CloudRequestHeaders.forPage 生成。
  Map<String, String>? get headers => null;
}
