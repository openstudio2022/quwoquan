import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将 canonical Post 合同投影收口为 App 内容 ViewData 的唯一边界。
final class ContentPostProjectionMapper {
  const ContentPostProjectionMapper();

  /// [openSurface] 与 [presentationRecipe] 来自同一列表项的信封；不下发信封的
  /// 操作（详情、离线快照）保持缺席，端侧不按内容类型补猜。
  ContentPostViewData toDto(
    ContentPostProjection projection, {
    ContentUiSurface? openSurface,
    FeedPresentationRecipe? presentationRecipe,
  }) {
    return ContentPostViewData.fromWire(
      projection,
      openSurface: openSurface,
      presentationRecipe: presentationRecipe,
    );
  }
}
