import 'package:flutter/material.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart'
    show appImageLoadErrorKey;
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_failure_state.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/signed_grant_image.dart';
export 'package:quwoquan_app/runtime/transport/media/media_delivery_binding.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_binding.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show MediaDeliveryAccessMode;

/// 媒体消费点的唯一 typed 分流入口（DEC-033）。
///
/// 页面与设计系统组件把 typed 绑定交给本入口，由它按投影声明分流；分流判据只有
/// 一处实现，消费点不再各自写 `accessMode == signedGrant ? ... : ...`。
///
/// 四种输入形态各自独立判否，不合并为「缺席」：
/// - signedGrant 且资产身份在场：走 [SignedGrantImage]，grant 兑换与换签收敛在
///   coordinator 一处；
/// - signedGrant 但资产身份缺席：投影自相矛盾，落显式判否终态，**不回退公开
///   路径**——私有资产走公开 URL 会把授权判定悄悄跳过；
/// - typed public（含具名 legacy adapter 已适配出的 public）且 URL 在场：走
///   [publicBuilder]；
/// - accessMode 缺席/未知但仍带 URL 或资产身份：contract failure，落判否终态；
/// - 全部字段均缺席：宿主没给任何可渲染取值，落缺席终态。
class MediaDeliveryImage extends StatelessWidget {
  const MediaDeliveryImage({
    super.key,
    required this.binding,
    required this.kind,
    required this.publicBuilder,
    this.width,
    this.height,
    this.fit,
    this.placeholder,
    this.errorWidget,
    this.absentWidget,
    this.signedReadyBuilder,
    this.onLoadSucceeded,
    this.onLoadFailed,
  });

  final MediaDeliveryBinding binding;

  /// 媒体交付种类（头像面用 avatar，内容图与封面用 image）。
  final MediaDeliveryKind kind;

  /// 公开交付的渲染委托。公开候选推导、CDN 预设与占位差异逐消费点不同，由调用方
  /// 在此承载；私有交付不经此委托。
  final Widget Function(BuildContext context, String publicUrl) publicBuilder;

  final double? width;
  final double? height;
  final BoxFit? fit;
  final Widget? placeholder;

  /// 私有交付失败与投影自相矛盾共用的判否终态件。
  final Widget? errorWidget;

  /// 宿主未给出任何可渲染取值时的缺席终态件。缺省时不占位、不渲染。
  final Widget? absentWidget;

  /// 私有交付换签成功后的渲染委托。缺席时用标准网络图片渲染短签 URL。
  ///
  /// 消费面自带加载体验语义时两路都应交回该面渲染，否则同一处会出现
  /// 「公开走消费面体验、私有走通用体验」两套观感。
  final Widget Function(
    BuildContext context,
    String deliveryUrl,
    String cacheIdentity,
  )?
  signedReadyBuilder;

  final VoidCallback? onLoadSucceeded;
  final void Function(Object error)? onLoadFailed;

  @override
  Widget build(BuildContext context) {
    if (binding.isSignedGrant) {
      return SignedGrantImage(
        assetId: binding.assetId,
        kind: kind,
        accessMode: MediaDeliveryAccessMode.signedGrant,
        width: width,
        height: height,
        fit: fit,
        placeholder: placeholder,
        errorWidget: errorWidget,
        readyBuilder: signedReadyBuilder,
        onLoadSucceeded: onLoadSucceeded,
        onLoadFailed: onLoadFailed,
      );
    }
    if (binding.isSignedGrantWithoutAsset || binding.isUnsupportedPrivateHls) {
      // 私有资产没有资产身份就换不到 grant；回退公开 URL 会把授权判定跳过，
      // 因此这里停在判否终态。重试不会让资产身份出现，故不给恢复动作。
      return _terminal(
        KeyedSubtree(
          key: appImageLoadErrorKey,
          child: errorWidget ?? const MediaDeliveryFailureState(),
        ),
      );
    }
    if (binding.isPublic) {
      final publicUrl = binding.publicUrl.trim();
      if (publicUrl.isEmpty) {
        return _terminal(absentWidget ?? const SizedBox.shrink());
      }
      return publicBuilder(context, publicUrl);
    }
    if (binding.isContractFailure) {
      return _terminal(
        KeyedSubtree(
          key: appImageLoadErrorKey,
          child: errorWidget ?? const MediaDeliveryFailureState(),
        ),
      );
    }
    return _terminal(absentWidget ?? const SizedBox.shrink());
  }

  Widget _terminal(Widget child) {
    if (width == null && height == null) {
      return child;
    }
    return SizedBox(width: width, height: height, child: child);
  }
}
