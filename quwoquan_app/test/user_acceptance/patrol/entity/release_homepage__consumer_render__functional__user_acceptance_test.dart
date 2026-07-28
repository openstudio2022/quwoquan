import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import '../../../support/release_homepage_uat_cases.dart';

const _encodedReleaseUatCases = String.fromEnvironment(
  'QWQ_RELEASE_HOMEPAGE_UAT_CASES_B64',
);
const _visibleElementTimeout = Duration(seconds: 20);
const _pageLoadTimeout = Duration(seconds: 45);
const _pollInterval = Duration(milliseconds: 500);
const _galleryScrollSettle = Duration(milliseconds: 300);
const _galleryScrollOffset = Offset(0, -600);
const _galleryScrollAttempts = 16;

void main() {
  patrolTest(
    'release_homepage_consumer_render',
    tags: ['t4', 'entity-homepage', 'release-consumer'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: _visibleElementTimeout,
      printLogs: true,
    ),
    ($) async {
      final homepages = parseReleaseHomepageUatCases(_encodedReleaseUatCases);
      await launchPatrolAppOnce($);

      for (final homepage in homepages) {
        await patrolGoTo(
          $,
          AppRoutePaths.homepageDetail(id: homepage.homepageId),
        );
        final detailLoaded = await _waitFor(
          $,
          find.byKey(TestKeys.homepageDetailPage),
          terminalFailure: find.byType(AppPageErrorState),
        );
        final boundaryDiagnostic = detailLoaded
            ? ''
            : await _diagnoseHomepageBoundary($, homepage.homepageId);
        expect(
          detailLoaded,
          isTrue,
          reason:
              '${homepage.title} detail must load from Gamma; '
              '${_pageFailureSummary($)}; $boundaryDiagnostic',
        );
        expect(find.byKey(TestKeys.homepageDetailPage), findsOneWidget);

        await patrolGoTo(
          $,
          AppRoutePaths.homepageIntroduction(id: homepage.homepageId),
        );
        expect(
          await _waitFor($, find.text('认识${homepage.title}')),
          isTrue,
          reason: '${homepage.title} introduction must load from Gamma',
        );
        expect(find.text('认识${homepage.title}'), findsOneWidget);
        expect(
          await _scrollUntilVisible(
            $,
            find.text(ObjectHomepageText.objectIntroSourceTitle),
          ),
          isTrue,
          reason: '${homepage.title} source disclosure must be reachable',
        );
      }
    },
  );
}

Future<String> _diagnoseHomepageBoundary(
  PatrolIntegrationTester $,
  String homepageId,
) async {
  final navigator = find.byType(Navigator).evaluate();
  if (navigator.isEmpty) {
    return 'boundary=no-navigator';
  }
  final container = ProviderScope.containerOf(navigator.first);
  final actor = container.read(homepageQueryActorContextProvider);
  final repository = container.read(homepageFacetSetProvider);
  final introductionRepository = container.read(
    homepageIntroductionRepositoryProvider,
  );
  final diagnostics = <String>[];

  Future<void> probe(
    String operation,
    Future<Object?> Function() invoke,
  ) async {
    try {
      await invoke();
      diagnostics.add('$operation=pass');
    } catch (error) {
      final result = error is CloudException
          ? _cloudFailureDiagnostic(error)
          : error.runtimeType.toString();
      diagnostics.add('$operation=$result');
    }
  }

  await probe('detail', () => repository.getHomepageDetail(homepageId));
  await probe('shell', () => repository.getHomepageShell(homepageId));
  await probe(
    'bundle',
    () => repository.getObjectPageBundle(
      homepageId,
      referralSource: ReferralSource.entityPage.value,
    ),
  );
  await probe(
    'introduction',
    () => introductionRepository.getHomepageIntroduction(homepageId),
  );
  return 'actor=account:${actor.accountId == null ? 'no' : 'yes'}'
      '/persona:${actor.personaId == null ? 'no' : 'yes'}; '
      'boundary=${diagnostics.join(',')}';
}

String _cloudFailureDiagnostic(CloudException error) {
  final failure = error.runtimeFailure;
  final cause = error.cause;
  final argumentDetail = cause is ArgumentError
      ? 'argument:${cause.name ?? 'unnamed'}:${cause.message ?? 'invalid'}'
      : '';
  final safeAttributes = failure.context.attributes
      .where(
        (attribute) =>
            const {'errorType', 'requestPath'}.contains(attribute.key),
      )
      .map((attribute) => '${attribute.key}:${attribute.value}')
      .join('|');
  final details = <String>[
    if (safeAttributes.isNotEmpty) safeAttributes,
    if (argumentDetail.isNotEmpty) argumentDetail,
  ].join('|');
  return details.isEmpty ? failure.code : '${failure.code}[$details]';
}

Future<bool> _waitFor(
  PatrolIntegrationTester $,
  Finder finder, {
  Finder? terminalFailure,
}) async {
  await $.pump();
  final deadline = DateTime.now().add(_pageLoadTimeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) {
      return true;
    }
    if (terminalFailure?.evaluate().isNotEmpty ?? false) {
      return false;
    }
    await $.pump(_pollInterval);
  }
  return false;
}

String _pageFailureSummary(PatrolIntegrationTester $) {
  final errors = find.byType(AppPageErrorState);
  if (errors.evaluate().isEmpty) {
    return 'no terminal page error was rendered';
  }
  final semantic = $.tester.widget<AppPageErrorState>(errors.first).semantic;
  return 'code=${semantic.sourceCode ?? 'unmapped'}, '
      'recovery=${semantic.recoveryAction?.name ?? 'none'}, '
      'message=${semantic.message}';
}

Future<bool> _scrollUntilVisible(
  PatrolIntegrationTester $,
  Finder finder,
) async {
  for (var attempt = 0; attempt < _galleryScrollAttempts; attempt += 1) {
    if (finder.evaluate().isNotEmpty) {
      return true;
    }
    final list = find.byType(ListView);
    if (list.evaluate().isEmpty) {
      return false;
    }
    await $.tester.drag(list.first, _galleryScrollOffset);
    await $.pump(_galleryScrollSettle);
  }
  return finder.evaluate().isNotEmpty;
}
