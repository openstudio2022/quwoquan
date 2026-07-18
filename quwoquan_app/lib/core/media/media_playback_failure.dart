import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/media/media_candidate_failure.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 面向消费者的播放失败场景；不泄露媒体栈、证书或网络拓扑细节。
enum VideoPlaybackUserScene {
  network,
  temporary,
  busy,
  unavailable,
  unsupported,
}

class VideoPlaybackCopy {
  const VideoPlaybackCopy({required this.title, this.message});

  final String title;
  final String? message;
}

/// 一次播放尝试的确定性失败结果。
///
/// 所有候选源都可记录自己的失败类别，但 UI 与观测只消费按固定优先级选出的 [kind]。
/// 该对象不保存 URL、原始异常文本或任何用户数据。
class MediaPlaybackFailure {
  const MediaPlaybackFailure._({
    required this.kind,
    required this.observedKinds,
    required this.candidatesTried,
  });

  factory MediaPlaybackFailure.fromKind(
    MediaCandidateFailureKind kind, {
    int candidatesTried = 0,
  }) {
    return MediaPlaybackFailure._(
      kind: kind,
      observedKinds: <MediaCandidateFailureKind>[kind],
      candidatesTried: candidatesTried,
    );
  }

  factory MediaPlaybackFailure.select(
    Iterable<MediaCandidateFailureKind> observedKinds, {
    required int candidatesTried,
  }) {
    final values = observedKinds.toSet().toList(growable: false);
    if (values.isEmpty) {
      return MediaPlaybackFailure.fromKind(
        MediaCandidateFailureKind.noPlayableSource,
        candidatesTried: candidatesTried,
      );
    }
    for (final candidate in _selectionPriority) {
      if (values.contains(candidate)) {
        return MediaPlaybackFailure._(
          kind: candidate,
          observedKinds: values,
          candidatesTried: candidatesTried,
        );
      }
    }
    return MediaPlaybackFailure._(
      kind: values.first,
      observedKinds: values,
      candidatesTried: candidatesTried,
    );
  }

  static const List<MediaCandidateFailureKind> _selectionPriority =
      <MediaCandidateFailureKind>[
        MediaCandidateFailureKind.http404,
        MediaCandidateFailureKind.http4xx,
        MediaCandidateFailureKind.decoderInitialization,
        MediaCandidateFailureKind.http5xx,
        MediaCandidateFailureKind.networkUnavailable,
        MediaCandidateFailureKind.controllerSlotTimeout,
        MediaCandidateFailureKind.noPlayableSource,
        MediaCandidateFailureKind.certificateVerifyFailed,
        MediaCandidateFailureKind.handshakeTerminated,
        MediaCandidateFailureKind.connectionRefused,
        MediaCandidateFailureKind.dnsNxdomain,
        MediaCandidateFailureKind.other,
      ];

  final MediaCandidateFailureKind kind;
  final List<MediaCandidateFailureKind> observedKinds;
  final int candidatesTried;

  VideoPlaybackUserScene get userScene {
    return switch (kind) {
      MediaCandidateFailureKind.networkUnavailable =>
        VideoPlaybackUserScene.network,
      MediaCandidateFailureKind.http5xx => VideoPlaybackUserScene.busy,
      MediaCandidateFailureKind.http404 ||
      MediaCandidateFailureKind.http4xx => VideoPlaybackUserScene.unavailable,
      MediaCandidateFailureKind.decoderInitialization =>
        VideoPlaybackUserScene.unsupported,
      _ => VideoPlaybackUserScene.temporary,
    };
  }

  ContentErrorCode get errorCode {
    return switch (userScene) {
      VideoPlaybackUserScene.network =>
        ContentErrorCode.mediaPlaybackNetworkUnavailable,
      VideoPlaybackUserScene.temporary =>
        ContentErrorCode.mediaPlaybackTemporarilyUnavailable,
      VideoPlaybackUserScene.busy => ContentErrorCode.mediaPlaybackServiceBusy,
      VideoPlaybackUserScene.unavailable =>
        ContentErrorCode.mediaPlaybackUnavailable,
      VideoPlaybackUserScene.unsupported =>
        ContentErrorCode.mediaPlaybackUnsupported,
    };
  }

  RuntimeFailure get runtimeFailure {
    return RuntimeFailure(
      code: errorCode.code,
      semanticReason: kind.name,
      transportStatus: errorCode.httpStatus,
      origin: RuntimeFailureOrigin.localClient,
      kind: _runtimeFailureKind,
      nature: _runtimeFailureNature,
      location: const RuntimeFailureLocation(
        businessObject: 'content.post',
        functionModule: 'media_playback',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'mediaFailureKind', value: kind.name),
          RuntimeContextAttribute(
            key: 'candidatesTried',
            value: candidatesTried.toString(),
          ),
        ],
      ),
      recovery: RuntimeRecoveryDirective(
        action: errorCode.recoveryAction,
        afterSeconds: errorCode.recoveryAfterSeconds,
      ),
    );
  }

  RuntimeRecoveryDecision get recoveryDecision {
    return const DefaultRuntimeRecoveryPolicy().decide(
      runtimeFailure,
      const EntryContext(
        kind: 'media_playback',
        entryId: 'video',
        actorType: 'viewer',
        actorId: '',
        surfaceId: 'VideoPlayerWidget',
      ),
      const BoundaryContext(
        boundary: 'native_video_player',
        stage: 'initialize',
        remainingBudget: 0,
      ),
    );
  }

  bool get isRetryable =>
      recoveryDecision.action == RuntimeRecoveryAction.retry;

  bool get shouldNegativeCache {
    return kind == MediaCandidateFailureKind.http404 ||
        kind == MediaCandidateFailureKind.http4xx;
  }

  VideoPlaybackCopy get copy {
    return switch (userScene) {
      VideoPlaybackUserScene.network => const VideoPlaybackCopy(
        title: UITextConstants.videoPlaybackNetworkTitle,
      ),
      VideoPlaybackUserScene.temporary => const VideoPlaybackCopy(
        title: UITextConstants.videoPlaybackTemporaryTitle,
      ),
      VideoPlaybackUserScene.busy => const VideoPlaybackCopy(
        title: UITextConstants.videoPlaybackTemporaryTitle,
      ),
      VideoPlaybackUserScene.unavailable => const VideoPlaybackCopy(
        title: UITextConstants.videoPlaybackUnavailableTitle,
        message: UITextConstants.videoPlaybackUnavailableMessage,
      ),
      VideoPlaybackUserScene.unsupported => const VideoPlaybackCopy(
        title: UITextConstants.videoPlaybackUnsupportedTitle,
        message: UITextConstants.videoPlaybackUnsupportedMessage,
      ),
    };
  }

  RuntimeFailureKind get _runtimeFailureKind {
    return switch (userScene) {
      VideoPlaybackUserScene.network => RuntimeFailureKind.network,
      VideoPlaybackUserScene.temporary ||
      VideoPlaybackUserScene.busy => RuntimeFailureKind.unavailable,
      VideoPlaybackUserScene.unavailable => RuntimeFailureKind.notFound,
      VideoPlaybackUserScene.unsupported => RuntimeFailureKind.unsupported,
    };
  }

  RuntimeFailureNature get _runtimeFailureNature {
    return switch (userScene) {
      VideoPlaybackUserScene.network ||
      VideoPlaybackUserScene.temporary ||
      VideoPlaybackUserScene.busy => RuntimeFailureNature.transient,
      VideoPlaybackUserScene.unavailable ||
      VideoPlaybackUserScene.unsupported => RuntimeFailureNature.permanent,
    };
  }
}
