import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart'
    show ConversationAssetView;

/// 群空间相册/文件宫格的真实承接面：消费 `ListConversationAssets` 读面
/// （Message owner 事实 + MediaAsset 交付字段），相册为网格、文件为列表。
class ConversationAssetsSheet extends ConsumerStatefulWidget {
  const ConversationAssetsSheet({
    super.key,
    required this.conversationId,
    required this.kind,
    this.onOpenImage,
    this.onOpenFile,
  });

  final String conversationId;

  /// image 或 file（契约 `ChatListConversationAssetsQuery.kind`）。
  final String kind;

  /// 点击图片行为（复用会话页全屏大图链）。
  final void Function(ConversationAssetView asset)? onOpenImage;

  /// 点击文件行为（复用会话页系统打开链）。
  final void Function(ConversationAssetView asset)? onOpenFile;

  static Future<void> show(
    BuildContext context, {
    required String conversationId,
    required String kind,
    void Function(ConversationAssetView asset)? onOpenImage,
    void Function(ConversationAssetView asset)? onOpenFile,
  }) {
    return showAppBottomModal<void>(
      context: context,
      builder: (_) => ConversationAssetsSheet(
        conversationId: conversationId,
        kind: kind,
        onOpenImage: onOpenImage,
        onOpenFile: onOpenFile,
      ),
    );
  }

  @override
  ConsumerState<ConversationAssetsSheet> createState() =>
      _ConversationAssetsSheetState();
}

class _ConversationAssetsSheetState
    extends ConsumerState<ConversationAssetsSheet> {
  List<ConversationAssetView> _items = const <ConversationAssetView>[];
  bool _loading = true;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final page = await ref
          .read(chatMessageRepositoryProvider)
          .listConversationAssets(
            conversationId: widget.conversationId,
            kind: widget.kind,
          );
      if (!mounted) return;
      setState(() {
        _items = page.items;
        _loading = false;
        _failed = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _failed = true;
      });
    }
  }

  bool get _isAlbum => widget.kind == 'image';

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final primary = SettingsSemanticConstants.conversationSheetPrimaryLabelColor(
      isDark,
    );
    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: SettingsSemanticConstants.conversationSheetPanelBackground(
        isDark,
      ),
      contentPadding: EdgeInsets.all(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
      maxHeightRatio: AppSpacing.modalSheetMaxHeightRatio,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            _isAlbum
                ? ChatText.groupCapabilityAlbum
                : ChatText.groupCapabilityFile,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: FontWeight.w600,
              color: primary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupLg),
          Flexible(child: _buildBody(primary)),
        ],
      ),
    );
  }

  Widget _buildBody(Color primary) {
    if (_loading) {
      return const AppSkeletonListRows(rowCount: 3);
    }
    if (_failed) {
      return AppEmptyState(
        icon: CupertinoIcons.exclamationmark_circle,
        title: ChatText.chatMediaUnavailable,
        actionLabel: ChatText.chatRetrySendMessage,
        onAction: () {
          setState(() => _loading = true);
          unawaited(_load());
        },
        actionKey: const ValueKey<String>('conversation_assets_retry'),
      );
    }
    if (_items.isEmpty) {
      return AppEmptyState(
        icon: _isAlbum ? CupertinoIcons.photo_on_rectangle : CupertinoIcons.doc,
        title: _isAlbum
            ? ChatText.groupAlbumEmpty
            : ChatText.groupFilesEmpty,
      );
    }
    if (_isAlbum) {
      return GridView.builder(
        shrinkWrap: true,
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 3,
          crossAxisSpacing: 2,
          mainAxisSpacing: 2,
        ),
        itemCount: _items.length,
        itemBuilder: (context, index) {
          final asset = _items[index];
          return GestureDetector(
            key: ValueKey<String>('conversation_asset_${asset.messageId}'),
            behavior: HitTestBehavior.opaque,
            onTap: () {
              Navigator.of(context).pop();
              widget.onOpenImage?.call(asset);
            },
            child: AppCachedNetworkImage(
              imageUrl: asset.mediaDeliveryUrl ?? '',
              fit: BoxFit.cover,
              cdnPreset: CdnImagePreset.inline,
              errorWidget: ColoredBox(
                color: AppColors.iosFill(context),
                child: Icon(
                  CupertinoIcons.photo,
                  color: primary.withValues(alpha: 0.4),
                ),
              ),
            ),
          );
        },
      );
    }
    return ListView.builder(
      shrinkWrap: true,
      itemCount: _items.length,
      itemBuilder: (context, index) {
        final asset = _items[index];
        final title = asset.fileName?.trim().isNotEmpty == true
            ? asset.fileName!.trim()
            : ChatText.chatPreviewFile;
        return CupertinoButton(
          key: ValueKey<String>('conversation_asset_${asset.messageId}'),
          padding: EdgeInsets.symmetric(
            vertical: AppSpacing.intraGroupSm,
            horizontal: AppSpacing.intraGroupXs,
          ),
          onPressed: () {
            Navigator.of(context).pop();
            widget.onOpenFile?.call(asset);
          },
          child: Row(
            children: [
              Icon(
                CupertinoIcons.doc_fill,
                size: AppSpacing.iconMedium,
                color: AppColors.primaryColor.withValues(alpha: 0.8),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosBody,
                        color: primary,
                      ),
                    ),
                    if (asset.senderName?.trim().isNotEmpty == true) ...[
                      SizedBox(height: AppSpacing.xs),
                      Text(
                        asset.senderName!.trim(),
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: primary.withValues(alpha: 0.6),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
