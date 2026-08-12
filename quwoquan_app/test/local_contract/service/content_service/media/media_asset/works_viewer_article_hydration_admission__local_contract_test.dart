// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_viewer_article_hydration_admission.dart';

void main() {
  test('快速切换严格串行并只保留最新 pending hydration', () async {
    final admission = WorksViewerArticleHydrationAdmission();
    final releases = <String, Completer<void>>{
      'article-a': Completer<void>(),
      'article-b': Completer<void>(),
      'article-c': Completer<void>(),
    };
    final leases = <String, WorksViewerArticleHydrationLease>{};
    final starts = <String>[];
    var executing = 0;
    var maxExecuting = 0;

    Future<WorksViewerArticleHydrationTerminal> run(
      WorksViewerArticleHydrationLease lease,
    ) async {
      leases[lease.postId] = lease;
      starts.add(lease.postId);
      executing += 1;
      maxExecuting = executing > maxExecuting ? executing : maxExecuting;
      try {
        // Deliberately ignore cancellation until the transport settles. The
        // admission layer must still not start another operation concurrently.
        await releases[lease.postId]!.future;
      } finally {
        executing -= 1;
      }
      return WorksViewerArticleHydrationTerminal.recovered;
    }

    final first = admission.schedule(postId: 'article-a', task: run);
    await Future<void>.delayed(Duration.zero);
    expect(starts, <String>['article-a']);
    expect(admission.activeCount, 1);

    final dropped = admission.schedule(postId: 'article-b', task: run);
    final latest = admission.schedule(postId: 'article-c', task: run);
    final droppedResult = await dropped;
    expect(
      droppedResult.terminal,
      WorksViewerArticleHydrationTerminal.superseded,
    );
    expect(leases['article-a']!.isCancelled, isTrue);
    expect(admission.pendingCount, 1);
    expect(starts, <String>['article-a']);

    releases['article-a']!.complete();
    final firstResult = await first;
    expect(
      firstResult.terminal,
      WorksViewerArticleHydrationTerminal.superseded,
    );
    await Future<void>.delayed(Duration.zero);
    expect(starts, <String>['article-a', 'article-c']);
    expect(maxExecuting, 1);

    releases['article-c']!.complete();
    final latestResult = await latest;
    expect(
      latestResult.terminal,
      WorksViewerArticleHydrationTerminal.recovered,
    );
    expect(firstResult.generation, lessThan(latestResult.generation));
    expect(droppedResult.generation, lessThan(latestResult.generation));
    expect(admission.activeCount, 0);
    expect(admission.pendingCount, 0);
    admission.dispose();
  });

  test('同一文章复入共用一个 operation，非文章 viewport 会取消', () async {
    final admission = WorksViewerArticleHydrationAdmission();
    final release = Completer<void>();
    late WorksViewerArticleHydrationLease lease;
    var starts = 0;

    Future<WorksViewerArticleHydrationTerminal> run(
      WorksViewerArticleHydrationLease value,
    ) async {
      starts += 1;
      lease = value;
      await release.future;
      return WorksViewerArticleHydrationTerminal.recovered;
    }

    final first = admission.schedule(postId: 'article-a', task: run);
    await Future<void>.delayed(Duration.zero);
    final duplicate = admission.schedule(postId: 'article-a', task: run);
    expect(identical(first, duplicate), isTrue);
    expect(starts, 1);

    admission.retainOnly('video-b');
    expect(lease.isCancelled, isTrue);
    release.complete();
    expect(
      (await first).terminal,
      WorksViewerArticleHydrationTerminal.superseded,
    );
    admission.dispose();
  });

  test('dispose 取消 active 并清除单一 pending', () async {
    final admission = WorksViewerArticleHydrationAdmission();
    final release = Completer<void>();
    late WorksViewerArticleHydrationLease activeLease;

    final active = admission.schedule(
      postId: 'article-a',
      task: (lease) async {
        activeLease = lease;
        await release.future;
        return WorksViewerArticleHydrationTerminal.recovered;
      },
    );
    await Future<void>.delayed(Duration.zero);
    final pending = admission.schedule(
      postId: 'article-b',
      task: (_) async {
        fail('disposed pending task must not start');
      },
    );

    admission.dispose();
    expect(activeLease.isCancelled, isTrue);
    expect(
      (await pending).terminal,
      WorksViewerArticleHydrationTerminal.superseded,
    );
    release.complete();
    expect(
      (await active).terminal,
      WorksViewerArticleHydrationTerminal.superseded,
    );
    expect(admission.activeCount, 0);
    expect(admission.pendingCount, 0);
  });

  test('task 异常以 stillBlocked 收口且后续 generation 继续 drain', () async {
    final admission = WorksViewerArticleHydrationAdmission();
    final blocked = admission.schedule(
      postId: 'article-a',
      task: (_) async => throw StateError('typed hydration failure'),
    );

    final blockedResult = await blocked;
    expect(
      blockedResult.terminal,
      WorksViewerArticleHydrationTerminal.stillBlocked,
    );
    expect(blockedResult.failure, isA<StateError>());

    final recovered = await admission.schedule(
      postId: 'article-b',
      task: (_) async => WorksViewerArticleHydrationTerminal.recovered,
    );
    expect(recovered.terminal, WorksViewerArticleHydrationTerminal.recovered);
    expect(recovered.generation, greaterThan(blockedResult.generation));
    expect(admission.activeCount, 0);
    expect(admission.pendingCount, 0);
    admission.dispose();
  });
}
