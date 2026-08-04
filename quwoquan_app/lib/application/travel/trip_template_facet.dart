import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 领队/组织者模板列表与“从模板创建 Trip”的唯一 App 应用边界。
abstract interface class TripTemplateFacet {
  Future<TripPlanTemplate> getTemplate(GetTripPlanTemplateQuery query);

  Future<TripPlanTemplateListSlice> listTemplates();

  Future<TripPlanTemplate> createTemplate(
    CreateTripPlanTemplateRequest request, {
    required String idempotencyKey,
  });

  Future<TripPlanTemplate> reviseTemplate(
    PutTripPlanTemplateRequest request, {
    required String idempotencyKey,
  });
}
