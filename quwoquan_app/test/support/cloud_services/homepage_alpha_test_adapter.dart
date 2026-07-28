import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_homepage/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CloudOperationCancellationSignal;

import 'repository_mock_reexports.dart';

/// local_contract 与 widget 测试使用的 App DTO 投影壳。
///
/// 所有 Homepage 状态和场景解析由 [AlphaHomepageFacet] 对象替身持有；
/// 此类只允许测试覆写窄 port 行为，不能回放生产 mock 数据。
class AlphaHomepageTestRepository extends HomepageFacetProjectionAdapter {
  AlphaHomepageTestRepository({AlphaHomepageFacet? facet})
    : this._(facet ?? AlphaHomepageFacet());

  AlphaHomepageTestRepository._(AlphaHomepageFacet facet)
    : super(
        query: facet,
        candidateWriter: facet,
        claimRequestWriter: facet,
        statusReportWriter: facet,
      );
}

/// 介绍页测试的无状态投影入口，避免测试重新持有任何 fixture 数据。
class AlphaHomepageIntroductionTestRepository
    implements HomepageIntroductionRepository {
  const AlphaHomepageIntroductionTestRepository();

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) {
    return HomepageIntroductionProjectionAdapter(
      query: AlphaHomepageFacet(),
    ).getHomepageIntroduction(homepageId, cancellation: cancellation);
  }
}

/// 仅供现有测试覆写的命名适配器；fixture 和行为仍由 [AlphaHomepageFacet] 提供。
class MockHomepageRepository extends AlphaHomepageTestRepository {
  MockHomepageRepository({super.facet});
}

/// 仅供现有介绍页测试注入；不持有任何业务 fixture 或 fallback。
class MockHomepageIntroductionRepository
    extends AlphaHomepageIntroductionTestRepository {
  const MockHomepageIntroductionRepository();
}
