// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/full-screen-search-shell-and-entry/spec.md#gwt-005
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-002
/// 公开 Content API 创建唯一真实 Post，等待 canonical Search 投影后，由
/// production App 正式结果页读取并在重入时再次确认同一 typed hit。
///
/// 当前 Gamma 尚无受治理的 search 分区故障/恢复编排，也没有同一 candidate 的
/// Android+iPhone ResultBundle，因此本 runner 不登记 readiness_case。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_network_results_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/search_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _gatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _disposableActorConfirmed = bool.fromEnvironment(
  'QWQ_SEARCH_CONTENT_DISPOSABLE_ACTOR_ACK',
);

void main() {
  patrolTest(
    'search_index_view_remote_content_projection_and_reentry_readback',
    tags: const ['user-acceptance', 'search', 'content', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: const PatrolTesterConfig(
      visibleTimeout: Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      _validateRuntimeInputs();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final contentHarness = await ContentApiContractHarness.create();
      SearchApiContractHarness? searchHarness;
      String? postId;

      try {
        searchHarness = await SearchApiContractHarness.create();
        final query = '真实搜索验收$suffix';
        final title = '$query 标题';
        final publication = await contentHarness.publication
            .submitPostPublication(
              SubmitContentPostPublicationCommand(
                publishIntentId: 'search-content-$suffix',
                localDraftId: 'search-content-draft-$suffix',
                contentType: ContentType.micro,
                contentIdentity: ContentIdentity.moment,
                title: title,
                body: '$query 正文只来自公开 Content command',
                visibility: Visibility.public,
              ),
            );
        postId = publication.postId;
        if (postId.trim().isEmpty) {
          throw StateError('SubmitPostPublication returned an empty postId');
        }

        final indexed = await _waitForCanonicalPostHit(
          searchHarness,
          query: query,
          postId: postId,
        );
        if (indexed.title != title ||
            indexed.objectType != SearchObjectType.contentPost.wireValue ||
            indexed.content?.postId != postId) {
          throw StateError('Canonical Search content projection drifted');
        }

        final session = contentHarness.session;
        final personaId = session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError(
            'Disposable Content actor requires an active persona',
          );
        }
        installPatrolAcceptanceSessionForRunner(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
          ownerId: session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);

        await _openCanonicalSearchResult($, query: query, title: title);
        await patrolGoTo($, AppRoutePaths.home);
        await _openCanonicalSearchResult($, query: query, title: title);
      } finally {
        try {
          if (postId != null) {
            await contentHarness.postDeletion.deletePost(
              postId: postId,
              idempotencyKey: 'search-content-cleanup-$suffix',
            );
          }
        } finally {
          try {
            await searchHarness?.close();
          } finally {
            await contentHarness.close();
          }
        }
      }
    },
  );
}

void _validateRuntimeInputs() {
  if (_apiContractEnv != 'gamma' || _appRuntimeEnv != _apiContractEnv) {
    throw StateError(
      'Search content UAT requires matching gamma APP_RUNTIME_ENV and '
      'API_CONTRACT_ENV',
    );
  }
  if (_patrolSessionMode.isNotEmpty) {
    throw StateError('Search content UAT installs its own disposable session');
  }
  final apiGateway = Uri.tryParse(_apiBaseUrl);
  final appGateway = Uri.tryParse(_gatewayBaseUrl);
  if (!_isAbsoluteHttps(apiGateway) || !_isAbsoluteHttps(appGateway)) {
    throw StateError(
      'Search content UAT requires absolute HTTPS API and App gateways',
    );
  }
  if (_normalizedGateway(apiGateway!) != _normalizedGateway(appGateway!)) {
    throw StateError(
      'Search content UAT requires App and API to use the same gateway',
    );
  }
  if (!_disposableActorConfirmed) {
    throw StateError(
      'Set QWQ_SEARCH_CONTENT_DISPOSABLE_ACTOR_ACK=true only when public '
      'DeletePost and CloseAccount cleanup are permitted',
    );
  }
}

bool _isAbsoluteHttps(Uri? value) =>
    value != null &&
    value.isAbsolute &&
    value.scheme == 'https' &&
    value.host.isNotEmpty;

String _normalizedGateway(Uri value) {
  final path = value.path.replaceFirst(RegExp(r'/+$'), '');
  return value.replace(path: path, query: null, fragment: null).toString();
}

Future<CanonicalSearchHit> _waitForCanonicalPostHit(
  SearchApiContractHarness harness, {
  required String query,
  required String postId,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 90));
  while (DateTime.now().isBefore(deadline)) {
    final response = await harness.search.search(
      CanonicalSearchQuery(
        sessionId: 'search-content-uat',
        query: query,
        mode: CanonicalSearchMode.result,
        limit: 50,
      ),
    );
    for (final hit in response.hits) {
      if (hit.objectId == postId) return hit;
    }
    await Future<void>.delayed(const Duration(milliseconds: 500));
  }
  throw StateError('Canonical Search index did not expose the published Post');
}

Future<void> _openCanonicalSearchResult(
  PatrolIntegrationTester $, {
  required String query,
  required String title,
}) async {
  await patrolGoTo(
    $,
    AppRoutePaths.globalSearchNetworkResults(query: query, tab: 'all'),
  );
  await $(find.byType(SearchNetworkResultsPage)).waitUntilVisible();
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(AppPageErrorState).evaluate().isNotEmpty) {
      fail('production Search result page entered an error terminal');
    }
    if (find.text(title).evaluate().isNotEmpty) {
      expect(find.text(title), findsOneWidget);
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('production Search page did not render the canonical content hit');
}
