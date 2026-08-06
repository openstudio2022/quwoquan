import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_facet_projection_adapter.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_introduction_projection_adapter.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_introduction_repository.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_command_writer.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_command_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CloudOperationCancellationSignal,
        HomepageClaimRequestView,
        HomepageIntroduction,
        HomepageStatusReportView;

import 'homepage_facets_typed_double.dart';

/// local_contract 与 widget 测试使用的 App DTO 投影壳。
///
/// 所有 Homepage 状态和场景解析由 [InMemoryHomepageFacet] 对象替身持有；
/// 此类只允许测试覆写窄 port 行为，不能回放生产 mock 数据。
class InMemoryHomepageTestRepository extends HomepageFacetProjectionAdapter
    implements
        HomepageClaimRequestCommandWriter,
        HomepageStatusReportCommandWriter {
  InMemoryHomepageTestRepository({InMemoryHomepageFacet? facet})
    : this._(facet ?? InMemoryHomepageFacet());

  InMemoryHomepageTestRepository._(this._facet)
    : super(query: _facet, candidateWriter: _facet);

  final InMemoryHomepageFacet _facet;

  @override
  Future<HomepageClaimRequestView> createClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) => _facet.createClaimRequest(homepageId: homepageId, draft: draft);

  @override
  Future<HomepageStatusReportView> createStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
  }) => _facet.createStatusReport(homepageId: homepageId, draft: draft);
}

/// 介绍页测试的无状态投影入口，避免测试重新持有任何 fixture 数据。
class InMemoryHomepageIntroductionTestRepository
    implements HomepageIntroductionRepository {
  const InMemoryHomepageIntroductionTestRepository();

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) {
    return HomepageIntroductionProjectionAdapter(
      query: InMemoryHomepageFacet(),
    ).getHomepageIntroduction(homepageId, cancellation: cancellation);
  }
}

/// 仅供现有测试覆写的命名适配器；fixture 和行为仍由 [InMemoryHomepageFacet] 提供。
class MockHomepageRepository extends InMemoryHomepageTestRepository {
  MockHomepageRepository({super.facet});
}

/// 仅供现有介绍页测试注入；不持有任何业务 fixture 或 fallback。
class MockHomepageIntroductionRepository
    extends InMemoryHomepageIntroductionTestRepository {
  const MockHomepageIntroductionRepository();
}
