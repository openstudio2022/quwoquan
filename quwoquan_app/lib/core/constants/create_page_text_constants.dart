/// 创作页专属文案门面。
///
/// 页面局部新增文案从 [UITextConstants] 大桶拆出，避免共享常量文件继续膨胀。
abstract final class CreatePageText {
  static const String photoPageTitle = '图片创作';
  static const String titleFieldLabel = '标题';

  static String maxImagesToast(int maxImages) => '最多添加 $maxImages 张图片';
}
