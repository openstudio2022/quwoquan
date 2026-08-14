// media_asset 对象 generated 错误码的端侧断言覆盖:
// media_not_found / media_in_use 与端侧本地播放语义码
// (media_playback_*,httpStatus == 0,不经 HTTP 传输)的枚举解析与
// 恢复语义,并以 media_not_found 走 CloudErrorMapper 映射负例。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

typedef _DeclaredCase = ({
  String wire,
  ContentErrorCode value,
  String recoveryAction,
  int recoveryAfterSeconds,
  int httpStatus,
});

void main() {
  const declared = <_DeclaredCase>[
    (
      wire: 'CONTENT.USER.media_not_found',
      value: ContentErrorCode.mediaNotFound,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 404,
    ),
    (
      wire: 'CONTENT.USER.media_in_use',
      value: ContentErrorCode.mediaInUse,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 409,
    ),
    (
      wire: 'CONTENT.SYSTEM.media_playback_network_unavailable',
      value: ContentErrorCode.mediaPlaybackNetworkUnavailable,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 0,
      httpStatus: 0,
    ),
    (
      wire: 'CONTENT.SYSTEM.media_playback_temporarily_unavailable',
      value: ContentErrorCode.mediaPlaybackTemporarilyUnavailable,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 0,
      httpStatus: 0,
    ),
    (
      wire: 'CONTENT.SYSTEM.media_playback_service_busy',
      value: ContentErrorCode.mediaPlaybackServiceBusy,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 0,
      httpStatus: 0,
    ),
    (
      wire: 'CONTENT.USER.media_playback_unavailable',
      value: ContentErrorCode.mediaPlaybackUnavailable,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 0,
    ),
    (
      wire: 'CONTENT.SYSTEM.media_playback_unsupported',
      value: ContentErrorCode.mediaPlaybackUnsupported,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 0,
    ),
  ];

  group('ContentErrorCode — media_asset 错误码契约', () {
    for (final entry in declared) {
      test('${entry.wire} 解析与恢复语义与声明一致', () {
        final parsed = ContentErrorCode.fromCode(entry.wire);
        expect(parsed, entry.value);
        expect(parsed.code, entry.wire);
        expect(parsed.httpStatus, entry.httpStatus);
        expect(parsed.recoveryAction, entry.recoveryAction);
        expect(parsed.recoveryAfterSeconds, entry.recoveryAfterSeconds);
        expect(ContentErrorMessages.zh[parsed], isNotEmpty);
        expect(ContentErrorMessages.en[parsed], isNotEmpty);
      });
    }

    test('播放语义码为端侧本地判定:httpStatus == 0 且瞬态类可 retry', () {
      const playbackCodes = <ContentErrorCode>[
        ContentErrorCode.mediaPlaybackNetworkUnavailable,
        ContentErrorCode.mediaPlaybackTemporarilyUnavailable,
        ContentErrorCode.mediaPlaybackServiceBusy,
        ContentErrorCode.mediaPlaybackUnavailable,
        ContentErrorCode.mediaPlaybackUnsupported,
      ];
      for (final code in playbackCodes) {
        expect(
          code.httpStatus,
          0,
          reason: '${code.code}: 播放语义码不经 HTTP 传输,不得声明传输状态',
        );
      }
      // 网络抖动/服务繁忙属瞬态,可重试;不支持/整体不可看属终态,提示用户换内容。
      expect(
        ContentErrorCode.mediaPlaybackNetworkUnavailable.recoveryAction,
        'retry',
      );
      expect(
        ContentErrorCode.mediaPlaybackServiceBusy.recoveryAction,
        'retry',
      );
      expect(
        ContentErrorCode.mediaPlaybackUnsupported.recoveryAction,
        'surface',
      );
      expect(
        ContentErrorCode.mediaPlaybackUnavailable.recoveryAction,
        'surface',
      );
    });
  });

  group('CloudErrorMapper — media_asset 代表性映射负例', () {
    test('404 media_not_found → typed 解析 + surface 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        404,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.USER.media_not_found',
          origin: 'user',
          kind: 'notFound',
          nature: 'permanent',
          businessObject: 'media_asset',
          functionModule: 'content',
          recoveryAction: 'surface',
          requestId: 'req-media-asset-errors-1',
          traceId: 'trace-media-asset-errors-1',
        ),
        requestPath: '/content/media/expired-asset',
      );

      expect(exception.code, 'CONTENT.USER.media_not_found');
      expect(exception.domainErrorCode?.domain, 'content');
      expect(exception.domainErrorCode?.value, ContentErrorCode.mediaNotFound);
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.notFound);
      expect(exception.runtimeFailure.transportStatus, 404);
      expect(exception.runtimeFailure.recovery.action, 'surface');
    });
  });
}
