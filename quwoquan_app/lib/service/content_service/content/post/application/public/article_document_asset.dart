// 文章素材的纯值类型。
//
// 从 article_document_models.dart 按职责拆出：本文件只声明单个素材的
// 不可变投影（身份、交付声明、版式与元数据几何），不含文档装配与节点
// 投影逻辑。消费方仍从 article_document_models.dart 导入。

class ArticleDocumentAsset {
  const ArticleDocumentAsset({
    required this.id,
    required this.offset,
    this.imageUrl = '',
    this.imageLayout = 'fullWidth',
    this.accessMode = '',
    this.caption = '',
    this.width,
    this.height,
  });

  final String id;
  final int offset;
  final String imageUrl;
  /// 交付访问模式（PostArticleAsset.accessMode，DEC-033）；空串为契约缺席。
  final String accessMode;
  final String imageLayout;
  final String caption;

  /// 资产声明的像素宽高（manifest `PostArticleAsset.width/height`）；
  /// 元数据缺席保持 null（REQ-017），不得塌陷为 0 或默认值。
  final int? width;
  final int? height;

  /// 元数据派生的宽高比；任一维缺席或非正即整体缺席（null），由消费方
  /// 统一走后备比例，禁止各自猜测。
  double? get metadataAspectRatio {
    final w = width;
    final h = height;
    if (w == null || h == null || w <= 0 || h <= 0) {
      return null;
    }
    return w / h;
  }

  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';
}
