import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show MediaDeliveryAccessMode;

/// release 媒体交付的端侧领域值（DEC-033）。
///
/// 「什么算私有」是一条领域判据而不是渲染细节：它决定该资产要不要换短签。
/// 因此绑定与其解析器留在 domain，渲染件只消费它，不得各自从 URL 形态反推。

/// 把文章投影里的 accessMode 字符串解析成 typed 声明（DEC-033/DEC-040）。
///
/// null/空串与未知值都保持 contract failure；只有具名 [legacyPublic] adapter 能把
/// 已确认的 legacy-public 投影显式迁成 public。消费面不得从 URL 形态或字段缺席
/// 猜 public。
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

  /// 明确声明为 typed public 的正常构造。public builder 只接受此状态。
  const MediaDeliveryBinding.public({
    this.assetId = '',
    required this.publicUrl,
  }) : accessMode = MediaDeliveryAccessMode.public;

  /// 已确认 legacy-public contract version 的唯一迁移 adapter。
  ///
  /// 调用者必须先在所属 decoder/version 边界确认 legacy 身份；本构造不会按 URL
  /// 形态猜测。正常新投影不得调用它。
  const MediaDeliveryBinding.legacyPublic({
    this.assetId = '',
    required this.publicUrl,
  }) : accessMode = MediaDeliveryAccessMode.public;

  /// 投影未给出任何绑定时的缺席绑定：既没有资产身份也没有公开 URL。
  const MediaDeliveryBinding.absent()
    : assetId = '',
      accessMode = null,
      publicUrl = '';

  /// release authority 下发的媒体资产标识；禁止以 postId/personaId 冒充。
  final String assetId;

  /// 投影 typed 声明的交付形态。null 是 contract failure，绝不代表 public。
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

  /// public builder 的唯一准入状态；具名 legacy adapter 也已显式适配成该 typed 值。
  bool get isPublic => accessMode == MediaDeliveryAccessMode.public;

  /// 非空 URL 却没有 typed accessMode：新投影契约失败，禁止公开 fallback。
  bool get isContractFailure =>
      accessMode == null && (assetId.isNotEmpty || publicUrl.trim().isNotEmpty);

  /// signed_grant 当前只支持 progressive 资源；HLS/DASH 需独立 authority。
  bool get isUnsupportedPrivateHls {
    if (accessMode != MediaDeliveryAccessMode.signedGrant) {
      return false;
    }
    final path =
        Uri.tryParse(publicUrl.trim())?.path.toLowerCase() ??
        publicUrl.trim().split('?').first.toLowerCase();
    return path.endsWith('.m3u8') ||
        path.endsWith('.mpd') ||
        path.contains('/manifest/');
  }

  /// 该绑定是否可能渲染出内容——供消费点决定是否占位，不用于选择交付路径。
  ///
  /// 私有绑定只看资产身份在场，不看公开 URL：私有资产本就没有公开 URL，
  /// 拿 URL 非空当「有图」会让私有封面在静态态整片消失。
  bool get hasRenderableSource =>
      (isSignedGrant && !isUnsupportedPrivateHls) ||
      (isPublic && publicUrl.trim().isNotEmpty) ||
      isContractFailure ||
      isSignedGrantWithoutAsset ||
      isUnsupportedPrivateHls;

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
