// spec_ref: specs/feature-tree/spec.md#uat-002
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/spec.md#sit-003
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-005
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-008
// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-005
// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-002
import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart'
    show contentPostDeleteIdempotencyKey;
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/providers/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';

const _pngBase64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==';
const _mp4Base64 =
    'AAAAJGZ0eXBpc29tAAACAGlzb21pc282aXNvMmF2YzFtcDQxAAAExG1vb3YAAABsbXZoZAAAAAAAAAAAAAAAAAAAA+gAAAAAAAEAAAEAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIAAAHndHJhawAAAFx0a2hkAAAAAwAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAQAAAAAAQAAAAEAAAAAABg21kaWEAAAAgbWRoZAAAAAAAAAAAAAAAAAAAKAAAAAAAVcQAAAAAAC1oZGxyAAAAAAAAAAB2aWRlAAAAAAAAAAAAAAAAVmlkZW9IYW5kbGVyAAAAAS5taW5mAAAAFHZtaGQAAAABAAAAAAAAAAAAAAAkZGluZgAAABxkcmVmAAAAAAAAAAEAAAAMdXJsIAAAAAEAAADuc3RibAAAAKJzdHNkAAAAAAAAAAEAAACSYXZjMQAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAQABAASAAAAEgAAAAAAAAAARVMYXZjNjIuMjguMTAyIGxpYngyNjQAAAAAAAAAAAAAABj//wAAACxhdmNDAULACv/hABVnQsAK2nsBEAAAAwAQAAADAKjxImoBAARozg/IAAAAEHBhc3AAAAABAAAAAQAAABBzdHRzAAAAAAAAAAAAAAAQc3RzYwAAAAAAAAAAAAAAFHN0c3oAAAAAAAAAAAAAAAAAAAAQc3RjbwAAAAAAAAAAAAABv3RyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAQEAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAVttZGlhAAAAIG1kaGQAAAAAAAAAAAAAAAAAAB9AAAAAAFXEAAAAAAAtaGRscgAAAAAAAAAAc291bgAAAAAAAAAAAAAAAFNvdW5kSGFuZGxlcgAAAAEGbWluZgAAABBzbWhkAAAAAAAAAAAAAAAkZGluZgAAABxkcmVmAAAAAAAAAAEAAAAMdXJsIAAAAAEAAADKc3RibAAAAH5zdHNkAAAAAAAAAAEAAABubXA0YQAAAAAAAAABAAAAAAAAAAAAAQAQAAAAAB9AAAAAAAA2ZXNkcwAAAAADgICAJQACAASAgIAXQBUAAAAAAB9AAAAfQAWAgIAFFYhW5QAGgICAAQIAAAAUYnRydAAAAAAAAB9AAAAfQAAAABBzdHRzAAAAAAAAAAAAAAAQc3RzYwAAAAAAAAAAAAAAFHN0c3oAAAAAAAAAAAAAAAAAAAAQc3RjbwAAAAAAAAAAAAAASG12ZXgAAAAgdHJleAAAAAAAAAABAAAAAQAAAAAAAAAAAAAAAAAAACB0cmV4AAAAAAAAAAIAAAABAAAAAAAAAAAAAAAAAAAAYnVkdGEAAABabWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAtaWxzdAAAACWpdG9vAAAAHWRhdGEAAAABAAAAAExhdmY2Mi4xMi4xMDIAAAD8bW9vZgAAABBtZmhkAAAAAAAAAAEAAABodHJhZgAAACR0ZmhkAAAAOQAAAAEAAAAAAAAE6AAADR8AAAJsAQEAAAAAABR0ZmR0AQAAAAAAAAAAAAAAAAAAKHRydW4AAAMFAAAAAgAAAQQCAAAAAAANHwAAAmwAAAgAAAAACQAAAHx0cmFmAAAAJHRmaGQAAAA5AAAAAgAAAAAAAAToAAAEAAAAAO8CAAAAAAAAFHRmZHQBAAAAAAAAAAAAAAAAAAA8dHJ1bgAAAwEAAAAFAAADeQAABAAAAADvAAAEAAAAANYAAAQAAAAAzAAABAAAAACkAAAAgAAAAAUAAAW3bWRhdAAAAlEGBf//TdxF6b3m2Ui3lizYINkj7u94MjY0IC0gY29yZSAxNjUgcjMyMjIgYjM1NjA1YSAtIEguMjY0L01QRUctNCBBVkMgY29kZWMgLSBDb3B5bGVmdCAyMDAzLTIwMjUgLSBodHRwOi8vd3d3LnZpZGVvbGFuLm9yZy94MjY0Lmh0bWwgLSBvcHRpb25zOiBjYWJhYz0wIHJlZj0xIGRlYmxvY2s9MDowOjAgYW5hbHlzZT0wOjAgbWU9ZGlhIHN1Ym1lPTAgcHN5PTEgcHN5X3JkPTEuMDA6MC4wMCBtaXhlZF9yZWY9MCBtZV9yYW5nZT0xNiBjaHJvbWFfbWU9MSB0cmVsbGlzPTAgOHg4ZGN0PTAgY3FtPTAgZGVhZHpvbmU9MjEsMTEgZmFzdF9wc2tpcD0xIGNocm9tYV9xcF9vZmZzZXQ9MCB0aHJlYWRzPTEgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0wIHdlaWdodHA9MCBrZXlpbnQ9MiBrZXlpbnRfbWluPTEgc2NlbmVjdXQ9MCBpbnRyYV9yZWZyZXNoPTAgcmM9Y3JmIG1idHJlZT0wIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRpbz0xLjQwIGFxPTAAgAAAABNliIQ6EYoAAhjxwABA9jgACHlgAAAABUGaID6U3gIATGF2YzYyLjI4LjEwMgACOKVS00bus/aPt8SVdy0SJEiRJINq2natp2radq4ztXGdq2menbFO2Kw7VtO1cZ2rjOVZTlW05VtNixOOxOVZSECECECESUZKMqjKpTJWlNdcrq7tzA3YpQJQMDAwMDGzcsssssspuWWWWWWU3LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLwBAJzZOR1EuhlEvBVkvn2+f/4v/P9euONatJ/0/T/8P/P8eeOtXd1n/T8/+n/z9dcca1Zr/0/P/p/9/rjjjjUvFl0UgcBl0ck4mmZsMVzTTL2NjZHZs2RLHIfrwXYIHCUYTrOdFVRjGoNHRRHQboHUKDdBp1UUHEatiIs2EfLct2ydC6Nr7GyKLYUvyJHBWXMs52I885znUpUalKnnnnnnVOqdU6p5551KnnVPOqeeedU6th55556CgupQic1hSJ3D8FOdUPNPzKnn5p/l8quYifqOhSAOAPydtgl6Jsl6Jol6Jft+f/w/8/x511rUjj/09//4v/P9euOtXesv/t+f/p/5/r1x1xxKxAZdF/GBmkzVMztmzKc77TSyIoYYubjFzD5CIvkPlFFF8p+PHjF8pvl8vlx2Hin48URFOgDLFEqqIKUFQXqd0+lcW9ZWTu6KJCESLWsiKKKKKKKKKIoiiiiiiLLFFFFFFFFFEMqCKIRBBVHqnRFF/og/BU5zsAW49Jk5JJErvIororoi5CItIiiiuii/eJBGkhISGPBLCoDgAQSdpQl2Lsj8X4D8Pt+f/T/5+uuOtXcb//p8/t+vtxrWrvWvHPv/Xz9cXq5JBdK65S88lKb2MuYy5555554PMeY8x55555jHnnng8x5mOabXrnrGuaSQrOxufidXIjKbSGr1xDY7F/R8542hof4P8f4P8f4P8f4P8f4H+P8f4D/H+P8f4B/j/H+IltYZDG+Pjx+Pj4+Pj4+Pj4+Pj4+Pj4+Pj44BGIG0cAAAAG5tZnJhAAAAK3RmcmEBAAAAAAAAAQAAAAAAAAABAAAAAAAAAAAAAAAAAAAE6AEBAQAAACt0ZnJhAQAAAAAAAAIAAAAAAAAAAQAAAAAAAAAAAAAAAAAABOgBAQEAAAAQbWZybwAAAAAAAABu';

void main() {
  patrolTest(
    'photo publication uses the production Remote page and processed readback',
    tags: const <String>['t4', 'content', 'media-publication', 'photo'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 15),
      printLogs: true,
    ),
    ($) => _runMediaPublicationJourney($, mediaKind: CreateMediaKind.images),
  );

  patrolTest(
    'video publication streams, normalizes, selects cover, and reads back',
    tags: const <String>['t4', 'content', 'media-publication', 'video'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 15),
      printLogs: true,
    ),
    ($) => _runMediaPublicationJourney($, mediaKind: CreateMediaKind.video),
  );

  patrolTest(
    'micro publication reaches result and canonical work browser through Remote',
    tags: const <String>['t4', 'content', 'text-publication', 'micro'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 15),
      printLogs: true,
    ),
    ($) => _runTextPublicationJourney($, publishAsArticle: false),
  );

  patrolTest(
    'article publication reaches result and canonical work browser through Remote',
    tags: const <String>['t4', 'content', 'text-publication', 'article'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 15),
      printLogs: true,
    ),
    ($) => _runTextPublicationJourney($, publishAsArticle: true),
  );
}

Future<void> _runMediaPublicationJourney(
  PatrolIntegrationTester $, {
  required CreateMediaKind mediaKind,
}) async {
  await launchPatrolAppOnce($);

  final navigator = find.byType(Navigator).evaluate().first;
  final container = ProviderScope.containerOf(navigator);
  await container.read(createDraftStoreProvider.future);
  container.read(postPublicationIntentQueueProvider);

  final nonce = DateTime.now().microsecondsSinceEpoch;
  final draftId = 'remote-media-uat-${mediaKind.name}-$nonce';
  final marker = 'remote media publication ${mediaKind.name} $nonce';
  final source = await _writeSource(mediaKind, nonce);
  String? postId;
  String? acceptedState;
  final subscription = container.listen<PostPublicationIntentQueueState>(
    postPublicationIntentQueueProvider,
    (_, next) {
      for (final intent in next.intents) {
        if (intent.command.localDraftId != draftId) {
          continue;
        }
        final observedPostId = intent.postId?.trim() ?? '';
        if (observedPostId.isNotEmpty) {
          postId = observedPostId;
        }
        final state = intent.publicationState?.wireValue;
        if (state == 'pending_review' || state == 'published') {
          acceptedState = state;
        }
      }
    },
    fireImmediately: true,
  );

  try {
    final initial = CreateEditorState.initial(
      editorKind: CreateEditorKind.media,
      draftFlowKind: mediaKind == CreateMediaKind.video
          ? CreateDraftFlowKind.video
          : CreateDraftFlowKind.image,
    );
    final state = initial.copyWith(
      mediaKind: mediaKind,
      imagePaths: mediaKind == CreateMediaKind.images
          ? <String>[source.path]
          : const <String>[],
      videoPath: mediaKind == CreateMediaKind.video ? source.path : '',
      originalVideoPath: mediaKind == CreateMediaKind.video ? source.path : '',
      videoDurationMs: mediaKind == CreateMediaKind.video ? 1000 : 0,
      videoWidth: mediaKind == CreateMediaKind.video ? 32 : 0,
      videoHeight: mediaKind == CreateMediaKind.video ? 32 : 0,
      videoCoverStrategy: 'first_frame',
      body: marker,
      draftId: draftId,
    );
    await container
        .read(createDraftStoreProvider.notifier)
        .saveDraft(
          CreateDraft(
            id: draftId,
            updatedAtMs: DateTime.now().millisecondsSinceEpoch,
            state: state,
            sourceType: mediaKind == CreateMediaKind.video ? 'video' : 'image',
          ),
          currentDraftId: draftId,
        );

    await patrolGoTo(
      $,
      '${AppRoutePaths.createPathTemplate}?draftId=${Uri.encodeQueryComponent(draftId)}',
    );
    await $(
      TestKeys.createPage,
    ).waitUntilVisible(timeout: const Duration(seconds: 20));
    await $(TestKeys.createPublishButton).tap();
    await $(
      TestKeys.createPublishConfirmSheet,
    ).waitUntilVisible(timeout: const Duration(seconds: 15));
    await $(TestKeys.createPublishConfirmButton).tap();
    await _waitForPublicationResultWithRecovery($);
    final accepted = await _waitFor(
      $,
      () => postId != null && acceptedState != null,
      timeout: const Duration(minutes: 5),
    );
    expect(
      accepted,
      isTrue,
      reason: '后台重试必须把真实媒体发布推进到 pending_review/published 并保留 postId。',
    );
    final expectedResultTitle = acceptedState == 'pending_review'
        ? CreationText.publishResultPendingReviewTitle
        : CreationText.publishResultSuccessTitle;
    final resultPresentationConverged = await _waitFor(
      $,
      () => find.text(expectedResultTitle).evaluate().isNotEmpty,
      timeout: const Duration(seconds: 10),
    );
    expect(
      resultPresentationConverged,
      isTrue,
      reason: '结果面必须如实区分待审核与已发布，不能把受理伪装成公开成功。',
    );
    await $(TestKeys.createPublishResultDoneButton).tap();

    final detail = await container
        .read(workBrowserContentPostDetailReaderProvider)
        .getPost(postId: postId!);
    expect(detail.post.normalizedBody, marker);
    if (mediaKind == CreateMediaKind.images) {
      expect(detail.post.imageUrls, isNotEmpty);
      expect(detail.post.coverUrl?.trim(), isNotEmpty);
    } else {
      expect(detail.post.videoUrl?.trim(), isNotEmpty);
      expect(detail.post.thumbnailUrl?.trim(), isNotEmpty);
    }

    await patrolGoTo($, AppRoutePaths.workBrowser(workId: postId!));
    final viewerLoaded = await _waitFor(
      $,
      () => find
          .byKey(const ValueKey<String>('works-top-rail'))
          .evaluate()
          .isNotEmpty,
      timeout: const Duration(seconds: 30),
    );
    expect(viewerLoaded, isTrue, reason: '发布结果必须能由真实作品页加载，不能只验证 API 回执。');
    expect(
      find.byKey(const ValueKey<String>('work-browser-entry-error')),
      findsNothing,
    );
  } finally {
    subscription.close();
    if (postId != null) {
      await container
          .read(contentPostDeleteCommandWriterProvider)
          .deletePost(
            postId: postId!,
            idempotencyKey: contentPostDeleteIdempotencyKey(postId!),
          );
    }
    await container
        .read(createDraftStoreProvider.notifier)
        .deleteDraft(draftId);
    if (await source.exists()) {
      await source.delete();
    }
  }
}

Future<void> _runTextPublicationJourney(
  PatrolIntegrationTester $, {
  required bool publishAsArticle,
}) async {
  await launchPatrolAppOnce($);

  final navigator = find.byType(Navigator).evaluate().first;
  final container = ProviderScope.containerOf(navigator);
  await container.read(createDraftStoreProvider.future);
  container.read(postPublicationIntentQueueProvider);

  final nonce = DateTime.now().microsecondsSinceEpoch;
  final contentType = publishAsArticle ? 'article' : 'micro';
  final draftId = 'remote-text-uat-$contentType-$nonce';
  final marker = 'remote $contentType publication $nonce';
  final body = publishAsArticle
      ? '$marker\n\n${List<String>.filled(6, '这是一段远端文章发布验收正文。').join()}'
      : marker;
  String? postId;
  String? acceptedState;
  final subscription = container.listen<PostPublicationIntentQueueState>(
    postPublicationIntentQueueProvider,
    (_, next) {
      for (final intent in next.intents) {
        if (intent.command.localDraftId != draftId) {
          continue;
        }
        final observedPostId = intent.postId?.trim() ?? '';
        if (observedPostId.isNotEmpty) {
          postId = observedPostId;
        }
        final state = intent.publicationState?.wireValue;
        if (state == 'pending_review' || state == 'published') {
          acceptedState = state;
        }
      }
    },
    fireImmediately: true,
  );

  try {
    final state =
        CreateEditorState.initial(
          editorKind: CreateEditorKind.text,
          draftFlowKind: CreateDraftFlowKind.article,
        ).copyWith(
          draftId: draftId,
          title: publishAsArticle ? marker : '',
          body: body,
        );
    await container
        .read(createDraftStoreProvider.notifier)
        .saveDraft(
          CreateDraft(
            id: draftId,
            updatedAtMs: DateTime.now().millisecondsSinceEpoch,
            state: state,
            sourceType: 'text',
          ),
          currentDraftId: draftId,
        );

    await patrolGoTo(
      $,
      '${AppRoutePaths.createPathTemplate}?draftId=${Uri.encodeQueryComponent(draftId)}',
    );
    await $(
      TestKeys.createPage,
    ).waitUntilVisible(timeout: const Duration(seconds: 20));
    await $(TestKeys.createPublishButton).tap();
    await $(
      TestKeys.createPublishConfirmSheet,
    ).waitUntilVisible(timeout: const Duration(seconds: 15));
    await $(TestKeys.createPublishConfirmButton).tap();
    await _waitForPublicationResultWithRecovery($);
    expect(
      await _waitFor(
        $,
        () => postId != null && acceptedState != null,
        timeout: const Duration(minutes: 2),
      ),
      isTrue,
      reason: '真实 $contentType 发布必须推进到受理状态并保留 canonical postId。',
    );
    await $(TestKeys.createPublishResultDoneButton).tap();

    final detail = await container
        .read(workBrowserContentPostDetailReaderProvider)
        .getPost(postId: postId!);
    expect(detail.post.type, contentType);
    expect(
      publishAsArticle ? detail.post.title : detail.post.normalizedBody,
      contains(marker),
      reason: 'Remote 回读必须保留 $contentType 的 canonical 内容。',
    );

    await patrolGoTo($, AppRoutePaths.workBrowser(workId: postId!));
    expect(
      await _waitFor(
        $,
        () => find
            .byKey(const ValueKey<String>('works-top-rail'))
            .evaluate()
            .isNotEmpty,
        timeout: const Duration(seconds: 30),
      ),
      isTrue,
      reason: '$contentType 发布结果必须能进入 canonical workBrowser。',
    );
    expect(
      find.byKey(const ValueKey<String>('work-browser-entry-error')),
      findsNothing,
    );
  } finally {
    subscription.close();
    if (postId != null) {
      await container
          .read(contentPostDeleteCommandWriterProvider)
          .deletePost(
            postId: postId!,
            idempotencyKey: contentPostDeleteIdempotencyKey(postId!),
          );
    }
    await container
        .read(createDraftStoreProvider.notifier)
        .deleteDraft(draftId);
  }
}

Future<void> _waitForPublicationResultWithRecovery(
  PatrolIntegrationTester $,
) async {
  const maxUserRetries = 2;
  for (var retry = 0; retry <= maxUserRetries; retry++) {
    final outcomeVisible = await _waitFor(
      $,
      () =>
          find.byKey(TestKeys.createPublishResultSheet).evaluate().isNotEmpty ||
          find.text(ContentText.tryAgain).evaluate().isNotEmpty,
      timeout: const Duration(seconds: 90),
    );
    expect(outcomeVisible, isTrue, reason: '媒体发布必须在 90 秒内进入结果面或展示可执行的结构化恢复动作。');
    if (find.byKey(TestKeys.createPublishResultSheet).evaluate().isNotEmpty) {
      return;
    }
    expect(retry, lessThan(maxUserRetries), reason: '连续恢复后仍未进入发布结果面。');
    await $(ContentText.tryAgain).tap();
    await $(
      TestKeys.createPublishConfirmSheet,
    ).waitUntilVisible(timeout: const Duration(seconds: 20));
    await $(TestKeys.createPublishConfirmButton).tap();
  }
  fail('媒体发布恢复循环未进入终态。');
}

Future<File> _writeSource(CreateMediaKind mediaKind, int nonce) async {
  final isVideo = mediaKind == CreateMediaKind.video;
  final file = File(
    '${Directory.systemTemp.path}/qwq-remote-media-uat-$nonce.'
    '${isVideo ? 'mp4' : 'png'}',
  );
  await file.writeAsBytes(
    base64Decode(isVideo ? _mp4Base64 : _pngBase64),
    flush: true,
  );
  return file;
}

Future<bool> _waitFor(
  PatrolIntegrationTester $,
  bool Function() predicate, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (predicate()) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return predicate();
}
