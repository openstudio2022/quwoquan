// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/spec.md#sit-001
// readiness_case: report_my_reports_page_app_uat
/// Patrol UAT：当前 Persona 的举报生命周期由 production Remote 读取。
///
/// create-then-readback：先经公开 Content command 创建真实 Post 与举报，
/// 再断言 MyReports 页面渲染该举报的公开生命周期状态。空态不是本用例的
/// 合法终态——防止「环境无数据时空页也算通过」；显式空态场景由
/// `my_reports_empty_state_is_explicit` 用例单独承载。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

void main() {
  patrolTest(
    'my_reports_page_renders_created_report_lifecycle',
    tags: ['user-acceptance', 'content', 'report'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'Patrol user_acceptance tests must run with API_CONTRACT_ENV=gamma',
      );
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final harness = await ContentApiContractHarness.create();
      String? postId;
      try {
        // 前置事实只经公开 command：先发一个 Post 作为举报对象，再创建举报。
        final publication = await harness.publication.submitPostPublication(
          SubmitContentPostPublicationCommand(
            publishIntentId: 'my-reports-uat-$suffix',
            localDraftId: 'my-reports-uat-draft-$suffix',
            contentType: ContentType.micro,
            contentIdentity: ContentIdentity.moment,
            title: '举报生命周期验收 $suffix',
            body: '举报对象正文只来自公开 Content command',
            visibility: Visibility.public,
          ),
        );
        postId = publication.postId;
        expect(postId.trim(), isNotEmpty, reason: 'publication must return postId');

        await harness.reports.createReport(
          CreateContentReportCommand(
            targetId: postId,
            targetType: ReportTargetType.post,
            reason: ReportReason.spam,
            description: 'my_reports UAT create-then-readback $suffix',
          ),
        );

        final session = harness.session;
        final personaId = session.activePersona?.personaId.trim() ?? '';
        expect(personaId, isNotEmpty, reason: 'disposable actor needs persona');
        installPatrolAcceptanceSessionForRunner(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
          ownerId: session.ownerId,
          personaId: personaId,
        );
        await launchPatrolAppOnce($);
        await patrolGoTo($, AppRoutePaths.myReports);

        await $(
          find.text(ContentText.myReportsTitle),
        ).waitUntilVisible(timeout: const Duration(seconds: 15));

        final lifecycleVisible = await _waitForNonEmptyLifecycleRow($);
        expect(
          lifecycleVisible,
          isTrue,
          reason:
              'MyReports must render the created report in a public lifecycle '
              'state; an empty page is not a legal terminal for this journey',
        );
      } finally {
        try {
          if (postId != null) {
            await harness.postDeletion.deletePost(
              postId: postId,
              idempotencyKey: 'my-reports-uat-cleanup-$suffix',
            );
          }
        } finally {
          await harness.close();
        }
      }
    },
  );
}

/// 只接受具体生命周期状态；空态标题出现不构成通过条件。
Future<bool> _waitForNonEmptyLifecycleRow(PatrolIntegrationTester $) async {
  final lifecycle = <Finder>[
    find.text(ContentText.reportStatusPending),
    find.text(ContentText.reportStatusReviewing),
    find.text(ContentText.reportStatusResolved),
    find.text(ContentText.reportStatusDismissed),
  ];
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (lifecycle.any((finder) => finder.evaluate().isNotEmpty)) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}
