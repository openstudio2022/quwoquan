import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_failure_state.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show MediaDeliveryAccessMode;

/// 私有媒体图片消费的唯一桥接原子（DEC-033）。
///
/// 页面与设计系统组件只向本原子传 typed 交付绑定（assetId + kind +
/// accessMode），grant 兑换、校验、缓存、单飞与强制换签全部收敛在
/// SignedMediaDeliveryCoordinator 一处；本原子只承载三态呈现与单次换签
/// 重试的编排，不各自实现 grant 逻辑。视频路不经本原子。
///
/// 三态语义：
/// - 等待兑换/换签中渲染占位（携带 [appImageLoadPlaceholderKey]）；
/// - 兑换成功后渲染 [AppCachedNetworkImage]，URL 为短签交付地址、
///   缓存键为稳定资产身份（签名 query 不参与缓存键）；
/// - 兑换失败或重试仍败渲染显式错误恢复态（携带 [appImageLoadErrorKey]），
///   不静默空白，也不把失败吞成 public 回退——失败与缺席是两个状态。
class SignedGrantImage extends ConsumerStatefulWidget {
  const SignedGrantImage({
    super.key,
    required this.assetId,
    required this.kind,
    required this.accessMode,
    this.width,
    this.height,
    this.fit,
    this.placeholder,
    this.errorWidget,
    this.readyBuilder,
    this.onLoadSucceeded,
    this.onLoadFailed,
  });

  /// release authority 下发的媒体资产标识；禁止以 postId/personaId 冒充。
  final String assetId;

  /// 媒体交付种类（头像面用 avatar，内容图与封面用 image）。
  final MediaDeliveryKind kind;

  /// 投影 typed 声明的交付形态。本原子只服务 signedGrant；
  /// public/null 属调用方分流契约误用，呈现错误态且不触达 coordinator。
  final MediaDeliveryAccessMode? accessMode;

  final double? width;
  final double? height;
  final BoxFit? fit;
  final Widget? placeholder;
  final Widget? errorWidget;

  /// 换签成功后的渲染委托。缺席时用标准网络图片渲染短签 URL。
  ///
  /// 消费面自带加载体验语义（如文章图的静默占位阈值、延迟指示与失败重试）时
  /// 由此交回该面渲染：换签编排只此一处，渲染不被换签绕过。委托拿到的是已
  /// 校验的短签地址与稳定缓存身份，签名 query 不得进入缓存键。
  final Widget Function(
    BuildContext context,
    String deliveryUrl,
    String cacheIdentity,
  )?
  readyBuilder;

  final VoidCallback? onLoadSucceeded;
  final void Function(Object error)? onLoadFailed;

  @override
  ConsumerState<SignedGrantImage> createState() => _SignedGrantImageState();
}

enum _SignedGrantPhase { resolving, ready, failed }

class _SignedGrantImageState extends ConsumerState<SignedGrantImage> {
  _SignedGrantPhase _phase = _SignedGrantPhase.resolving;
  SignedMediaDeliveryLease? _lease;

  /// 字节 GET 失败后只允许一次强制换签，重试仍败即停在错误态，禁止循环。
  bool _retriedOnce = false;

  /// 失败是否源于调用方分流契约误用（public/缺席绑定进入本原子）。
  /// 这类判否重试不会消解，因此终态不给恢复动作。
  bool _failedFromContractMisuse = false;

  /// 绑定代际：绑定变更（didUpdateWidget）后使旧异步结果失效，防止旧兑换
  /// 覆盖新绑定的状态。
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _startResolve();
  }

  @override
  void didUpdateWidget(SignedGrantImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.assetId != widget.assetId ||
        oldWidget.kind != widget.kind ||
        oldWidget.accessMode != widget.accessMode) {
      setState(() {
        _retriedOnce = false;
        _startResolve();
      });
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
    final assetId = widget.assetId.trim();
    if (widget.accessMode != MediaDeliveryAccessMode.signedGrant ||
        assetId.isEmpty) {
      // 调用方分流契约误用（public/缺席绑定不应进入本原子）：呈现显式
      // 错误态，不触达 coordinator，也不猜一条公开 URL 顶替。
      _phase = _SignedGrantPhase.failed;
      _failedFromContractMisuse = true;
      _lease = null;
      return;
    }
    _phase = _SignedGrantPhase.resolving;
    _failedFromContractMisuse = false;
    _lease = null;

    ref
        .read(signedMediaDeliveryCoordinatorProvider)
        .resolve(
          assetId: assetId,
          kind: widget.kind,
          accessMode: MediaDeliveryAccessMode.signedGrant,
        )
        .then(
          (lease) {
            if (!mounted || generation != _generation) {
              return;
            }
            setState(() {
              _phase = _SignedGrantPhase.ready;
              _lease = lease;
            });
          },
          onError: (Object error) {
            if (!mounted || generation != _generation) {
              return;
            }
            setState(() {
              _phase = _SignedGrantPhase.failed;
              _lease = null;
            });
            widget.onLoadFailed?.call(error);
          },
        );
  }

  /// 字节 GET 失败（含 401/403 与其余加载失败）的单次强制换签编排。
  ///
  /// 回调发生在 AppCachedNetworkImage 的 errorWidget build 期间，状态切换
  /// 必须推迟出当前 build；用 microtask 而非 post-frame 回调，因为后者不
  /// 自行调度新帧，在无后续帧时会让换签悬空。
  void _handleByteLoadFailed(Object error) {
    if (!mounted) {
      return;
    }
    final generation = _generation;
    Future<void>.microtask(() {
      if (!mounted || generation != _generation) {
        return;
      }
      _refreshOnceOrFail(error);
    });
  }

  Future<void> _refreshOnceOrFail(Object error) async {
    if (_retriedOnce) {
      setState(() {
        _phase = _SignedGrantPhase.failed;
        _lease = null;
      });
      widget.onLoadFailed?.call(error);
      return;
    }
    _retriedOnce = true;
    setState(() {
      _phase = _SignedGrantPhase.resolving;
      _lease = null;
    });
    final generation = _generation;
    try {
      final lease = await ref
          .read(signedMediaDeliveryCoordinatorProvider)
          .refresh(assetId: widget.assetId.trim(), kind: widget.kind);
      if (!mounted || generation != _generation) {
        return;
      }
      setState(() {
        _phase = _SignedGrantPhase.ready;
        _lease = lease;
      });
    } on Object catch (refreshError) {
      if (!mounted || generation != _generation) {
        return;
      }
      setState(() {
        _phase = _SignedGrantPhase.failed;
        _lease = null;
      });
      widget.onLoadFailed?.call(refreshError);
    }
  }

  @override
  Widget build(BuildContext context) {
    switch (_phase) {
      case _SignedGrantPhase.failed:
        return _sized(
          KeyedSubtree(
            key: appImageLoadErrorKey,
            child: widget.errorWidget ?? _defaultErrorState(context),
          ),
        );
      case _SignedGrantPhase.resolving:
        return _sized(
          KeyedSubtree(
            key: appImageLoadPlaceholderKey,
            child:
                widget.placeholder ??
                Container(color: AppColors.iosGroupedSurface(context)),
          ),
        );
      case _SignedGrantPhase.ready:
        final lease = _lease!;
        final deliveryUrl = lease.deliveryUri.toString();
        final readyBuilder = widget.readyBuilder;
        if (readyBuilder != null) {
          return readyBuilder(context, deliveryUrl, lease.cacheIdentity);
        }
        return AppCachedNetworkImage(
          imageUrl: deliveryUrl,
          // 短签 URL 单候选直传：签名 URL 不进入公开候选推导，也不经
          // CDN 变体处理器（DEC-033），cdnPreset 保持 none。
          imageUrlCandidates: <String>[deliveryUrl],
          // 稳定缓存身份：签名 query 随 TTL 轮换，不参与缓存键。
          cacheKey: lease.cacheIdentity,
          width: widget.width,
          height: widget.height,
          fit: widget.fit,
          placeholder: widget.placeholder,
          onLoadSucceeded: widget.onLoadSucceeded,
          onLoadFailed: _handleByteLoadFailed,
        );
    }
  }

  Widget _sized(Widget child) {
    if (widget.width == null && widget.height == null) {
      return child;
    }
    return SizedBox(width: widget.width, height: widget.height, child: child);
  }

  /// 判否终态：带恢复动作的失败呈现。
  ///
  /// 自动换签只允许一次（见 [_refreshOnceOrFail]），但终态必须给用户一条出路，
  /// 否则二次失败后这块区域永久不可恢复。此处的重试由用户点击驱动，不构成
  /// 自动循环，因此重置单次换签额度后重新兑换。
  Widget _defaultErrorState(BuildContext context) {
    if (_failedFromContractMisuse) {
      return const MediaDeliveryFailureState();
    }
    return MediaDeliveryFailureState(
      onRetry: () {
        setState(() {
          _retriedOnce = false;
          _startResolve();
        });
      },
    );
  }
}
