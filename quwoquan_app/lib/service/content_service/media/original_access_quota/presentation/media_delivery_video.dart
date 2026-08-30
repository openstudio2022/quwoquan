import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/runtime/transport/media/signed_video_delivery.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_failure_state.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart'
    show MediaDeliveryBinding;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show MediaDeliveryAccessMode;

/// 视频消费点的 typed 交付分流入口（DEC-033）。
///
/// 与图片路的 [MediaDeliveryImage] 对称：分流判据只此一处，消费点不再各自写
/// `accessMode == signedGrant ? 判否 : 播放`。
///
/// 四种输入形态各自独立判否，不合并为「缺席」：
/// - signedGrant 且资产身份在场：经 SignedMediaDeliveryCoordinator 兑换短签
///   地址后交给 [signedBuilder]。渐进式 MP4 的 Range 分段由原生播放器自行发起，
///   交付边缘按段复算签名，因此单签 URL 足够，不需要逐段换签；TTL 到期或签名
///   被拒时由播放器回调触发一次强制换签；
/// - signedGrant 但资产身份缺席：投影自相矛盾，落显式判否，**不回退公开路径**；
/// - typed public（含具名 legacy adapter 已适配出的 public）且 URL 在场：走
///   [publicBuilder]；
/// - null/unknown 或 private HLS：contract failure/unsupported typed terminal；
/// - 全部字段均缺席：宿主没给可播放取值，落缺席终态。
class MediaDeliveryVideo extends ConsumerStatefulWidget {
  const MediaDeliveryVideo({
    super.key,
    required this.binding,
    required this.publicBuilder,
    required this.signedBuilder,
    this.placeholder,
    this.errorWidget,
    this.absentWidget,
  });

  final MediaDeliveryBinding binding;

  /// 公开交付的播放委托。公开候选推导与 HLS 升级链由调用方承载。
  final Widget Function(BuildContext context, String publicUrl) publicBuilder;

  /// 私有交付换签成功后的播放委托。
  final Widget Function(BuildContext context, SignedVideoDelivery delivery)
  signedBuilder;

  final Widget? placeholder;
  final Widget? errorWidget;
  final Widget? absentWidget;

  @override
  ConsumerState<MediaDeliveryVideo> createState() => _MediaDeliveryVideoState();
}

enum _SignedVideoPhase { resolving, ready, failed }

class _MediaDeliveryVideoState extends ConsumerState<MediaDeliveryVideo> {
  _SignedVideoPhase _phase = _SignedVideoPhase.resolving;
  SignedMediaDeliveryLease? _lease;

  /// 播放失败后只允许一次强制换签，重试仍败即停在判否，禁止循环。
  bool _retriedOnce = false;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    if (widget.binding.isSignedGrant) {
      _startResolve();
    }
  }

  @override
  void didUpdateWidget(MediaDeliveryVideo oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.binding == widget.binding) {
      return;
    }
    _generation += 1;
    _lease = null;
    _retriedOnce = false;
    if (widget.binding.isSignedGrant) {
      setState(_startResolve);
    }
  }

  @override
  void dispose() {
    _generation += 1;
    super.dispose();
  }

  void _startResolve() {
    _generation += 1;
    final generation = _generation;
    _phase = _SignedVideoPhase.resolving;
    _lease = null;
    ref
        .read(signedMediaDeliveryCoordinatorProvider)
        .resolve(
          assetId: widget.binding.assetId,
          kind: MediaDeliveryKind.video,
          accessMode: MediaDeliveryAccessMode.signedGrant,
        )
        .then(
          (lease) {
            if (!mounted || generation != _generation) {
              return;
            }
            setState(() {
              _phase = _SignedVideoPhase.ready;
              _lease = lease;
            });
          },
          onError: (Object _) {
            if (!mounted || generation != _generation) {
              return;
            }
            setState(() {
              _phase = _SignedVideoPhase.failed;
              _lease = null;
            });
          },
        );
  }

  /// 播放失败后的单次强制换签：旧签名已被交付边缘拒绝，复用缓存只会重复失败。
  Future<void> _reSignOnceOrFail() async {
    if (!mounted) {
      return;
    }
    if (_retriedOnce) {
      setState(() {
        _phase = _SignedVideoPhase.failed;
        _lease = null;
      });
      return;
    }
    _retriedOnce = true;
    _generation += 1;
    final generation = _generation;
    setState(() {
      _phase = _SignedVideoPhase.resolving;
      _lease = null;
    });
    try {
      final lease = await ref
          .read(signedMediaDeliveryCoordinatorProvider)
          .refresh(
            assetId: widget.binding.assetId,
            kind: MediaDeliveryKind.video,
          );
      if (!mounted || generation != _generation) {
        return;
      }
      setState(() {
        _phase = _SignedVideoPhase.ready;
        _lease = lease;
      });
    } on Object {
      if (!mounted || generation != _generation) {
        return;
      }
      setState(() {
        _phase = _SignedVideoPhase.failed;
        _lease = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final binding = widget.binding;
    if (binding.isSignedGrantWithoutAsset ||
        binding.isUnsupportedPrivateHls ||
        binding.isContractFailure) {
      // 私有资产没有资产身份就换不到 grant；回退公开 URL 会把授权判定跳过。
      // 重试不会让资产身份出现，故不给恢复动作。
      return widget.errorWidget ??
          const MediaDeliveryFailureState(
            message: MediaText.signedDeliveryFailedMessage,
          );
    }
    if (binding.isSignedGrant) {
      switch (_phase) {
        case _SignedVideoPhase.resolving:
          return widget.placeholder ?? const SizedBox.shrink();
        case _SignedVideoPhase.failed:
          return widget.errorWidget ??
              MediaDeliveryFailureState(
                message: MediaText.signedDeliveryFailedMessage,
                onRetry: () {
                  setState(() {
                    _retriedOnce = false;
                    _startResolve();
                  });
                },
              );
        case _SignedVideoPhase.ready:
          final lease = _lease!;
          return widget.signedBuilder(
            context,
            SignedVideoDelivery(
              deliveryUri: lease.deliveryUri,
              cacheIdentity: lease.cacheIdentity,
              assetId: binding.assetId,
              onReSignRequested: () => _reSignOnceOrFail(),
            ),
          );
      }
    }
    if (binding.isPublic) {
      final publicUrl = binding.publicUrl.trim();
      if (publicUrl.isEmpty) {
        return widget.absentWidget ?? const SizedBox.shrink();
      }
      return widget.publicBuilder(context, publicUrl);
    }
    return widget.absentWidget ?? const SizedBox.shrink();
  }
}
