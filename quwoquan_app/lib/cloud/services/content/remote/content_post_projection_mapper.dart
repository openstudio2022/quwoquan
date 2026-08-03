import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将 canonical 云合同投影收口为 App 内容 ViewData 的唯一边界。
final class ContentPostProjectionMapper {
  const ContentPostProjectionMapper();

  ContentPostViewData toDto(ContentPostProjection projection) {
    return ContentPostViewData.fromWire(projection);
  }
}
