import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// TripPlan 创建命令的唯一 App 边界。模板列表与创建命令分离，
/// 避免 UI 同时承担 query 真相与幂等写入语义。
abstract interface class TripPlanCreationFacet {
  Future<TripPlanCommandResult> create(
    CreateTripPlanCommand command, {
    required String idempotencyKey,
  });

  Future<TripPlanCommandResult> createFromTemplate(
    CreateTripPlanFromTemplateCommand command, {
    required String idempotencyKey,
  });
}
