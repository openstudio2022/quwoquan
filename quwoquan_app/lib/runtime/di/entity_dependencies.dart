import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_command_remote.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_query_remote.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/adapters/homepage_claim_request_remote.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_command_writer.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_review/adapters/homepage_review_remote.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_review/application/public/homepage_review_operation_ports.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/adapters/homepage_status_report_remote.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_command_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef EntityHomepageInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      CloudOperationCancellationSignal? cancellation,
      DateTime? deadlineAt,
    });

/// 共享同一 Homepage Remote 实例的 public 查询 ports。
final class AppProductionHomepageQueryFacets {
  const AppProductionHomepageQueryFacets({
    required this.query,
    required this.introduction,
  });

  final HomepageQueryFacet query;
  final HomepageIntroductionQuery introduction;
}

/// 共享同一 Homepage Remote 实例的 public 命令 ports。
final class AppProductionHomepageCommandFacets {
  const AppProductionHomepageCommandFacets({
    required this.candidateWriter,
    required this.claimRequestWriter,
    required this.statusReportWriter,
  });

  final HomepageCandidateCommandWriter candidateWriter;
  final HomepageClaimRequestCommandWriter claimRequestWriter;
  final HomepageStatusReportCommandWriter statusReportWriter;
}

/// 共享同一 HomepageReview Remote 实例的 public ports。
final class AppProductionHomepageReviewFacets {
  const AppProductionHomepageReviewFacets({
    required this.commandWriter,
    required this.query,
  });

  final HomepageReviewCommandWriter commandWriter;
  final HomepageReviewQuery query;
}

/// entity domain 的唯一 production 装配入口。
final class EntityProductionComposition {
  const EntityProductionComposition._();

  /// 组合 Homepage owner 的 query capabilities。
  static AppProductionHomepageQueryFacets homepageQueryFacets({
    required GeneratedCloudOperationClient client,
    required EntityHomepageInvocationContextFactory detailInvocationContext,
    required EntityHomepageInvocationContextFactory
    introductionInvocationContext,
    required EntityHomepageInvocationContextFactory searchInvocationContext,
  }) {
    final homepageQuery = RemoteHomepageQueryAdapter(
      client: client,
      invocationContext: (clientPageId, surface, {cancellation, deadlineAt}) =>
          switch (surface) {
            HomepageQuerySurface.detail => detailInvocationContext(
              clientPageId,
              cancellation: cancellation,
              deadlineAt: deadlineAt,
            ),
            HomepageQuerySurface.introduction => introductionInvocationContext(
              clientPageId,
              cancellation: cancellation,
              deadlineAt: deadlineAt,
            ),
            HomepageQuerySurface.search => searchInvocationContext(
              clientPageId,
              cancellation: cancellation,
              deadlineAt: deadlineAt,
            ),
          },
    );
    return AppProductionHomepageQueryFacets(
      query: homepageQuery,
      introduction: homepageQuery,
    );
  }

  static AppProductionHomepageCommandFacets homepageCommandFacets({
    required GeneratedCloudOperationClient client,
    required HomepageCommandInvocationContextFactory invocationContext,
  }) {
    final candidateWriter = RemoteHomepageCommandWriter(
      client: client,
      invocationContext: invocationContext,
    );
    return AppProductionHomepageCommandFacets(
      candidateWriter: candidateWriter,
      claimRequestWriter: RemoteHomepageClaimRequestWriter(
        client: client,
        invocationContext: invocationContext,
      ),
      statusReportWriter: RemoteHomepageStatusReportWriter(
        client: client,
        invocationContext: invocationContext,
      ),
    );
  }

  static AppProductionHomepageReviewFacets homepageReviewFacets({
    required GeneratedCloudOperationClient client,
    required HomepageReviewInvocationContextFactory invocationContext,
  }) {
    final reviewFacet = RemoteHomepageReviewFacet(
      client: client,
      invocationContext: invocationContext,
    );
    return AppProductionHomepageReviewFacets(
      commandWriter: reviewFacet,
      query: reviewFacet,
    );
  }
}
