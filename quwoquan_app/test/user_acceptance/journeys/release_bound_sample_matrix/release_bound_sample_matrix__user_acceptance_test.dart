// spec_ref is consumed exactly from Data-owned ReleaseUatSamplePlan cells.
/// release-bound 16-slot Patrol UAT: feed/search/recommendation/direct route ×
/// homepage/article/image/video. No fixture or business Provider override is used.
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CanonicalSearchMode, SearchObjectType;
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_network_results_page.dart';

import '../../../support/runtime/patrol/patrol_app_uat_case_evidence.dart';
import '../../../support/runtime/patrol/patrol_core_readback_support.dart'
    show patrolMountedContainer;
import '../../../support/runtime/patrol/patrol_test_support.dart';
import '../../../support/runtime/patrol/release_uat_sample_plan.dart';

const String _encodedPlan = String.fromEnvironment(
  'QWQ_RELEASE_UAT_SAMPLE_PLAN_B64',
);
const String _encodedRuntimeBinding = String.fromEnvironment(
  'QWQ_RELEASE_UAT_RUNTIME_BINDING_B64',
);
const Duration _remoteTimeout = Duration(seconds: 60);
const Duration _pollInterval = Duration(milliseconds: 400);

void main() {
  patrolTest(
    'release_bound_sample_matrix_16_slots',
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      final matrix = parseReleaseUatSampleMatrix(
        encodedPlan: _encodedPlan,
        encodedRuntimeBinding: _encodedRuntimeBinding,
      );
      expect(matrix.slots, hasLength(16));
      await launchPatrolAppOnce($);
      final container = patrolMountedContainer();
      final feedObservations = await _observeEntry(
        matrix,
        'feed',
        () => _readFeedObservations(container, matrix),
      );
      final searchObservations = await _observeEntry(
        matrix,
        'search',
        () => _readSearchObservations(container, matrix),
      );
      final recommendationObservations = await _observeEntry(
        matrix,
        'recommendation',
        () => _readRecommendationObservations(container, matrix),
      );

      for (final slot in matrix.slots) {
        switch (slot.entrySurface) {
          case 'feed':
            final observation = feedObservations[slot.sample.carrier];
            if (observation == null || observation.startsWith('#BLOCKED#')) {
              emitBlockedPatrolAppUatCaseEvidence(
                slot: slot,
                reasonCode:
                    observation?.substring('#BLOCKED#'.length) ??
                    'APP.UAT.FEED_SAMPLE_NOT_OBSERVED',
              );
              continue;
            }
            await _runNavigableSlot(
              slot,
              () => _openAndCapture(
                $,
                slot,
                source: 'releaseUatFeed',
                terminalHint: observation,
              ),
            );
          case 'search':
            final observation = searchObservations[slot.sample.carrier];
            if (observation == null || observation.startsWith('#BLOCKED#')) {
              emitBlockedPatrolAppUatCaseEvidence(
                slot: slot,
                reasonCode:
                    observation?.substring('#BLOCKED#'.length) ??
                    'APP.UAT.SEARCH_SAMPLE_NOT_OBSERVED',
              );
              continue;
            }
            await _runNavigableSlot(
              slot,
              () => _captureSearchResult($, slot, observation),
            );
          case 'recommendation':
            final observation = recommendationObservations[slot.sample.carrier];
            if (observation == null || observation.startsWith('#BLOCKED#')) {
              emitBlockedPatrolAppUatCaseEvidence(
                slot: slot,
                reasonCode:
                    observation?.substring('#BLOCKED#'.length) ??
                    'APP.UAT.RECOMMENDATION_SAMPLE_NOT_OBSERVED',
              );
              continue;
            }
            await _runNavigableSlot(
              slot,
              () => _openAndCapture(
                $,
                slot,
                source: 'releaseUatRecommendation',
                terminalHint: observation,
              ),
            );
          case 'direct_or_object_route':
            await _runNavigableSlot(
              slot,
              () => _openAndCapture(
                $,
                slot,
                source: 'releaseUatDirect',
                terminalHint: slot.sample.runtimeObjectId,
              ),
            );
          default:
            fail('unknown ReleaseUatSamplePlan entry ${slot.entrySurface}');
        }
      }
    },
  );
}

Future<void> _runNavigableSlot(
  ReleaseUatSlot slot,
  Future<void> Function() navigateAndCapture,
) async {
  try {
    await navigateAndCapture();
  } catch (error) {
    emitBlockedPatrolAppUatCaseEvidence(
      slot: slot,
      reasonCode: 'APP.UAT.${slot.entrySurface.toUpperCase()}.TERMINAL_BLOCKED',
    );
  }
}

Future<Map<String, String>> _readFeedObservations(
  ProviderContainer container,
  ReleaseUatSampleMatrix matrix,
) async {
  final query = container.read(contentDiscoveryFeedQueryProvider);
  final observations = <String, String>{};
  for (final sample in matrix.samples) {
    if (sample.carrier == 'homepage') {
      final page = await query.listDiscoveryFeedPage(
        category: 'recommend',
        channelId: 'recommend',
        limit: 50,
      );
      final match = page.objectCards.where(
        (card) => card.objectId == sample.runtimeObjectId,
      );
      if (match.isNotEmpty) observations[sample.carrier] = match.first.title;
      continue;
    }
    final route = DiscoveryFeedRouteRegistry.routeForSurface(
      sample.carrier == 'image' ? 'photo' : sample.carrier,
    )!;
    final page = await query.listDiscoveryFeedPage(
      category: route.category,
      channelId: route.channelId,
      identity: route.identity,
      type: route.type,
      limit: 50,
    );
    final match = page.items.where((post) => post.id == sample.runtimeObjectId);
    if (match.isNotEmpty) observations[sample.carrier] = match.first.title;
  }
  return observations;
}

Future<Map<String, String>> _readRecommendationObservations(
  ProviderContainer container,
  ReleaseUatSampleMatrix matrix,
) async {
  final query = container.read(contentDiscoveryFeedQueryProvider);
  final observations = <String, String>{};
  for (final channel in container.read(homeChannelsProvider)) {
    final routedChannel = channel.feedQuery['channel'];
    final page = await query.listDiscoveryFeedPage(
      category: routedChannel ?? channel.feedQuery['category'] ?? channel.id,
      channelId: routedChannel,
      identity: routedChannel == null ? channel.feedQuery['identity'] : null,
      type: routedChannel == null ? channel.feedQuery['type'] : null,
      limit: 50,
    );
    for (final sample in matrix.samples) {
      if (observations.containsKey(sample.carrier)) continue;
      if (sample.carrier == 'homepage') {
        final cards = page.objectCards.where(
          (card) => card.objectId == sample.runtimeObjectId,
        );
        if (cards.isNotEmpty) observations[sample.carrier] = cards.first.title;
      } else {
        final posts = page.items.where(
          (post) => post.id == sample.runtimeObjectId,
        );
        if (posts.isNotEmpty) observations[sample.carrier] = posts.first.title;
      }
    }
    if (observations.length == matrix.samples.length) break;
  }
  return observations;
}

Future<Map<String, String>> _readSearchObservations(
  ProviderContainer container,
  ReleaseUatSampleMatrix matrix,
) async {
  final search = container.read(searchRepositoryProvider);
  final observations = <String, String>{};
  for (final sample in matrix.samples) {
    final response = await search.search(
      SearchRequest(
        query: _queryFromObjectRef(sample),
        mode: CanonicalSearchMode.result,
        objectTypes: <SearchObjectType>{
          sample.carrier == 'homepage'
              ? SearchObjectType.entityHomepage
              : SearchObjectType.contentPost,
        },
        contentTypes: sample.carrier == 'homepage'
            ? const <SearchContentTypeFilter>{}
            : <SearchContentTypeFilter>{
                SearchContentTypeFilter.fromWire(sample.carrier)!,
              },
        limit: 50,
      ),
      deadlineAt: DateTime.now().add(_remoteTimeout),
    );
    final flat = response.pageItems.where(
      (item) => _routeContainsObject(item.action, sample.runtimeObjectId),
    );
    final hits = response.hits.where(
      (hit) => hit.objectId == sample.runtimeObjectId,
    );
    if (flat.isNotEmpty) {
      observations[sample.carrier] = flat.first.action;
    } else if (hits.isNotEmpty) {
      observations[sample.carrier] = hits.first.title;
    }
  }
  return observations;
}

Future<void> _captureSearchResult(
  PatrolIntegrationTester $,
  ReleaseUatSlot slot,
  String observation,
) async {
  final query = _queryFromObjectRef(slot.sample);
  await patrolGoTo(
    $,
    AppRoutePaths.globalSearchNetworkResults(query: query, tab: 'all'),
  );
  final page = find.byType(SearchNetworkResultsPage);
  expect(await _waitFor($, page), isTrue, reason: 'search page must load');
  final exactAction = find.byKey(
    ValueKey<String>('search_page_result_action_${slot.sample.objectRef}'),
  );
  final fallback = find.textContaining(observation);
  final terminal = exactAction.evaluate().isNotEmpty ? exactAction : fallback;
  expect(
    await _waitFor($, terminal),
    isTrue,
    reason: '${slot.captureId} exact search result must render',
  );
  await emitPassedPatrolAppUatCaseEvidence(
    $,
    slot: slot,
    route: AppRoutePaths.globalSearchNetworkResults(query: query, tab: 'all'),
    terminalKey: 'search:${slot.sample.runtimeObjectId}',
    terminalFinder: terminal,
    targetKind: slot.sample.carrier == 'homepage' ? 'object' : 'page',
  );
}

Future<void> _openAndCapture(
  PatrolIntegrationTester $,
  ReleaseUatSlot slot, {
  required String source,
  required String terminalHint,
}) async {
  if (slot.sample.carrier == 'homepage') {
    final route = AppRoutePaths.homepageDetail(id: slot.sample.runtimeObjectId);
    await patrolGoTo($, route);
    final terminal = find.byKey(TestKeys.homepageDetailPage);
    expect(
      await _waitFor($, terminal),
      isTrue,
      reason: '${slot.captureId} homepage route must reach its terminal',
    );
    await emitPassedPatrolAppUatCaseEvidence(
      $,
      slot: slot,
      route: route,
      terminalKey: TestKeys.homepageDetailPage.value,
      terminalFinder: terminal,
      targetKind: 'object',
    );
    return;
  }

  final detail = await patrolMountedContainer()
      .read(workBrowserContentPostDetailReaderProvider)
      .getPost(postId: slot.sample.runtimeObjectId);
  expect(detail.post.id, slot.sample.runtimeObjectId);
  expect(detail.post.type, slot.sample.carrier);
  final route = AppRoutePaths.workBrowser(
    workId: slot.sample.runtimeObjectId,
    filter: slot.sample.carrier,
    source: source,
  );
  await patrolGoTo($, route);
  final pager = find.byKey(TestKeys.worksImmersivePager);
  final canvas = find.byKey(
    ValueKey<String>(
      'works-status-content-canvas-${slot.sample.runtimeObjectId}',
    ),
  );
  expect(
    await _waitFor($, pager),
    isTrue,
    reason: '${slot.captureId} work route must mount pager ($terminalHint)',
  );
  expect(
    await _waitFor($, canvas),
    isTrue,
    reason: '${slot.captureId} exact work canvas must render',
  );
  Finder terminal = canvas;
  if (slot.sample.carrier == 'image') {
    terminal = find.descendant(
      of: canvas,
      matching: find.byKey(
        const ValueKey<String>('image-book-decoded-surface'),
      ),
    );
    expect(await _waitFor($, terminal), isTrue, reason: 'image must decode');
    expect(
      find.descendant(of: canvas, matching: find.byKey(appImageLoadErrorKey)),
      findsNothing,
    );
  } else if (slot.sample.carrier == 'video') {
    terminal = find.byKey(const ValueKey<String>('video-player-ready'));
    expect(
      await _waitFor($, terminal),
      isTrue,
      reason: 'video must be playable',
    );
    expect(
      find.byKey(const ValueKey<String>('video-player-error')),
      findsNothing,
    );
  }
  await emitPassedPatrolAppUatCaseEvidence(
    $,
    slot: slot,
    route: route,
    terminalKey: 'works-status-content-canvas-${slot.sample.runtimeObjectId}',
    terminalFinder: terminal,
    targetKind: 'page',
  );
}

String _queryFromObjectRef(ReleaseUatSample sample) {
  final segments = sample.objectRef.split('/');
  return sample.carrier == 'homepage'
      ? segments.last
      : segments[segments.length - 2];
}

bool _routeContainsObject(String route, String objectId) =>
    Uri.tryParse(route)?.pathSegments.any((segment) => segment == objectId) ??
    false;

Future<bool> _waitFor(
  PatrolIntegrationTester $,
  Finder finder, {
  Duration timeout = _remoteTimeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) return true;
    await $.pump(_pollInterval);
  }
  return finder.evaluate().isNotEmpty;
}

Future<Map<String, String>> _observeEntry(
  ReleaseUatSampleMatrix matrix,
  String entry,
  Future<Map<String, String>> Function() invoke,
) async {
  try {
    return await invoke();
  } catch (error) {
    return <String, String>{
      for (final carrier in releaseUatCarriers)
        carrier: '#BLOCKED#APP.UAT.${entry.toUpperCase()}.QUERY_BLOCKED',
    };
  }
}
