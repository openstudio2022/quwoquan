import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_models.dart';
import 'package:quwoquan_app/core/media/media_candidate_failure.dart';
import 'package:quwoquan_app/core/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/core/media/media_playback_failure.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  group('MediaPlaybackFailure', () {
    test('证书失败只呈现连接未成功的用户语义与唯一重试动作', () {
      final failure = MediaPlaybackFailure.fromKind(
        MediaCandidateFailureKind.certificateVerifyFailed,
      );

      expect(failure.userScene, VideoPlaybackUserScene.temporary);
      expect(
        failure.userRecoveryGroup,
        AppUserRecoveryGroup.connectionUnavailable,
      );
      expect(failure.copy.title, SearchText.recoveryConnectionUnavailableTitle);
      expect(
        failure.copy.message,
        SearchText.recoveryConnectionUnavailableMessage,
      );
      expect(failure.isRetryable, isTrue);
      expect(failure.runtimeFailure.code, failure.errorCode.code);
      expect(failure.runtimeFailure.kind, RuntimeFailureKind.unavailable);
      expect(
        failure.copy.title,
        isNot(contains(RegExp(r'证书|CA|DNS|CDN|HTTP|Alpha|端口'))),
      );
    });

    test('404 选择不可观看场景且不显示无效重试', () {
      final failure = MediaPlaybackFailure.select(<MediaCandidateFailureKind>[
        MediaCandidateFailureKind.handshakeTerminated,
        MediaCandidateFailureKind.http404,
      ], candidatesTried: 1);

      expect(failure.kind, MediaCandidateFailureKind.http404);
      expect(failure.userScene, VideoPlaybackUserScene.unavailable);
      expect(
        failure.userRecoveryGroup,
        AppUserRecoveryGroup.contentUnavailable,
      );
      expect(failure.copy.title, SearchText.recoveryContentUnavailableTitle);
      expect(
        failure.copy.message,
        SearchText.recoveryContentUnavailableMessage,
      );
      expect(failure.isRetryable, isFalse);
      expect(failure.shouldNegativeCache, isTrue);
      expect(failure.runtimeFailure.kind, RuntimeFailureKind.notFound);
    });

    test('解码失败优先于短暂网络失败并映射为不可重试的支持提示', () {
      final failure = MediaPlaybackFailure.select(<MediaCandidateFailureKind>[
        MediaCandidateFailureKind.handshakeTerminated,
        MediaCandidateFailureKind.decoderInitialization,
      ], candidatesTried: 1);

      expect(failure.kind, MediaCandidateFailureKind.decoderInitialization);
      expect(failure.userScene, VideoPlaybackUserScene.unsupported);
      expect(
        failure.userRecoveryGroup,
        AppUserRecoveryGroup.contentUnavailable,
      );
      expect(failure.copy.title, SearchText.recoveryContentUnavailableTitle);
      expect(
        failure.copy.message,
        SearchText.recoveryContentUnavailableMessage,
      );
      expect(failure.isRetryable, isFalse);
      expect(failure.runtimeFailure.kind, RuntimeFailureKind.unsupported);
    });

    test('仅明确网络不可达才归为网络连接场景且不重复恢复指引', () {
      final failure = MediaPlaybackFailure.fromKind(
        MediaCandidateFailureKind.networkUnavailable,
      );

      expect(failure.userScene, VideoPlaybackUserScene.network);
      expect(failure.userRecoveryGroup, AppUserRecoveryGroup.connectNetwork);
      expect(failure.copy.title, SearchText.recoveryConnectNetworkTitle);
      expect(failure.copy.message, SearchText.recoveryConnectNetworkMessage);
      expect(failure.isRetryable, isTrue);
    });

    test('服务繁忙对用户采用服务未完成请求的恢复语义', () {
      final failure = MediaPlaybackFailure.fromKind(
        MediaCandidateFailureKind.http5xx,
      );

      expect(failure.userScene, VideoPlaybackUserScene.busy);
      expect(
        failure.userRecoveryGroup,
        AppUserRecoveryGroup.serviceUnavailable,
      );
      expect(failure.copy.title, SearchText.recoveryServiceUnavailableTitle);
      expect(
        failure.copy.message,
        SearchText.recoveryServiceUnavailableMessage,
      );
      expect(failure.isRetryable, isTrue);
    });
  });

  test('终端 404/4xx 才写入播放器负缓存', () {
    final cache = MediaLoadFailureCache();
    const identity = 'video|public-slice-key';

    cache.recordTerminalFailure(
      identity,
      kind: MediaCandidateFailureKind.handshakeTerminated,
    );
    expect(cache.shouldSkipNetwork(identity), isFalse);

    cache.recordTerminalFailure(
      identity,
      kind: MediaCandidateFailureKind.http404,
      statusCode: 404,
    );
    expect(cache.shouldSkipNetwork(identity), isTrue);
    expect(cache.activeFailure(identity)?.statusCode, 404);

    cache.clearIdentity(identity);
    expect(cache.shouldSkipNetwork(identity), isFalse);
  });
}
