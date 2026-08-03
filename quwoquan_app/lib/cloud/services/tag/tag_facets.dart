import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// App 调用 Tag 层级查询时采用的交互上限；服务端仍以 canonical request 校验为准。
abstract final class TagApiDefaults {
  static const int childrenLimit = 500;
}

/// App surface 使用的稳定 taxonomy 根引用；taxonomy 内容与发布身份仍由 tag-service 拥有。
abstract final class TagTaxonomyRefs {
  static const String chinaAdminRegionRoot = 'Topic/地理/行政区/中国';
  static const String careerOccupationRoot = 'Audience/用户/职业';
  static const String careerInterestRoot = 'Audience/用户/兴趣偏好';
}

/// TagNodeView 的 App application port。入参与返回值只使用 generated canonical wire。
abstract interface class TagCatalogQuery {
  Future<List<TagChildView>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  });

  Future<TagResolveView> resolveTag(String tagRef);

  Future<TagValidationResultView> validateRefs({
    required String expectedTaxonomyReleaseId,
    required List<String> tagRefs,
  });
}

/// TagFeedbackFact 的 App append port。
abstract interface class TagFeedbackCommandWriter {
  Future<TagFeedbackResultView> reportTagFeedback(
    ReportTagFeedbackCommand command,
  );
}
