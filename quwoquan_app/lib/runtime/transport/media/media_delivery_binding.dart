import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show MediaDeliveryAccessMode;

/// release 媒体交付的端侧领域值（DEC-033）。
///
/// 「什么算私有」是一条领域判据而不是渲染细节：它决定该资产要不要换短签。
/// 因此绑定与其解析器留在 domain，渲染件只消费它，不得各自从 URL 形态反推。

/// 把投影里的 accessMode 字符串解析成 typed 声明（DEC-033）。
///
/// 空串是契约 NULLABLE 的缺席态（存量 public 交付），保持 null；未知取值同样
/// 视为缺席而不是猜成 public——猜 public 会让私有资产走公开直连，把授权判定
/// 悄悄跳过。解析只此一处，消费面不各自写一遍字符串比较。
MediaDeliveryAccessMode? articleAssetAccessMode(String raw) {
  return switch (raw.trim()) {
    'signed_grant' => MediaDeliveryAccessMode.signedGrant,
    'public' => MediaDeliveryAccessMode.public,
    _ => null,
  };
}

/// 一个渲染点的 typed 媒体交付绑定（DEC-033）。
///
/// 绑定与 URL 的关联由服务端投影提供（`mediaItems` 的 mediaAssetId/accessMode、
/// 封面的 coverAssetId/coverAccessMode 等），App 不从 URL 形态推断交付形态。
class MediaDeliveryBinding {
  const MediaDeliveryBinding({
    required this.assetId,
    required this.accessMode,
    required this.publicUrl,
  });

  /// 投影未给出任何绑定时的缺席绑定：既没有资产身份也没有公开 URL。
  const MediaDeliveryBinding.absent()
    : assetId = '',
      accessMode = null,
      publicUrl = '';

  /// release authority 下发的媒体资产标识；禁止以 postId/personaId 冒充。
  final String assetId;

  /// 投影 typed 声明的交付形态。契约缺席即 null（存量 public 投影未带该字段）。
  final MediaDeliveryAccessMode? accessMode;

  /// 公开交付的渲染 URL。signedGrant 资产不经此字段取地址。
  final String publicUrl;

  /// 该绑定是否要走私有短签交付。
  ///
  /// 只有「typed 声明为 signedGrant 且资产身份在场」才成立。声明为 signedGrant
  /// 但资产身份缺席属投影自相矛盾，不在此处消解——由 [MediaDeliveryImage] 落显式
  /// 判否，不回退公开路径。
  bool get isSignedGrant =>
      accessMode == MediaDeliveryAccessMode.signedGrant && assetId.isNotEmpty;

  /// 声明为 signedGrant 但资产身份缺席：投影自相矛盾。
  bool get isSignedGrantWithoutAsset =>
      accessMode == MediaDeliveryAccessMode.signedGrant && assetId.isEmpty;

  /// 该绑定是否可能渲染出内容——供消费点决定是否占位，不用于选择交付路径。
  ///
  /// 私有绑定只看资产身份在场，不看公开 URL：私有资产本就没有公开 URL，
  /// 拿 URL 非空当「有图」会让私有封面在静态态整片消失。
  bool get hasRenderableSource => isSignedGrant || publicUrl.trim().isNotEmpty;

  /// 值相等：绑定序列被消费面当作页面身份使用（如沉浸图书的内容签名与
  /// didUpdateWidget 比较），引用相等会让同内容的新列表被误判为换页。
  @override
  bool operator ==(Object other) =>
      other is MediaDeliveryBinding &&
      other.assetId == assetId &&
      other.accessMode == accessMode &&
      other.publicUrl == publicUrl;

  @override
  int get hashCode => Object.hash(assetId, accessMode, publicUrl);
}
