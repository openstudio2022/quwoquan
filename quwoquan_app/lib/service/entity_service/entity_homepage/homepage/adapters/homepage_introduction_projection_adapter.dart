import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_contract_projection.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_introduction_repository.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将 pure-contract 介绍页投影为 App DTO；不绑定 Remote 或 alpha 实现。
class HomepageIntroductionProjectionAdapter
    implements HomepageIntroductionRepository {
  HomepageIntroductionProjectionAdapter({required this.query});

  final HomepageIntroductionQuery query;

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async {
    return homepageIntroductionFromContract(
      await query.getHomepageIntroduction(
        homepageId,
        cancellation: cancellation,
      ),
    );
  }
}
