// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';

/// 创作入口抽屉
///
/// 动作优先：先选动作，再在编辑器里决定点滴/作品。
class CreateEntrySheet extends ConsumerWidget {
  const CreateEntrySheet({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.onSelect,
    this.onOpenLegacyTab,
  });

  final bool isOpen;
  final VoidCallback onClose;
  final void Function(EditorStartAction action) onSelect;
  final void Function(String tabKey)? onOpenLegacyTab;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!isOpen) return const SizedBox.shrink();

    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final enableCreateActionEntry = ref.watch(
      contentFeatureFlagProvider('enable_create_action_entry'),
    );

    return Material(
      color: Colors.transparent,
      child: Stack(
        children: [
          GestureDetector(
            onTap: onClose,
            child: Container(color: Colors.black.withValues(alpha: 0.5)),
          ),
          Align(
            alignment: Alignment.bottomCenter,
            child: Container(
              constraints: BoxConstraints(
                maxHeight:
                    MediaQuery.of(context).size.height *
                    AppSpacing.createEntrySheetMaxHeightRatio,
              ),
              padding: EdgeInsets.only(
                bottom: MediaQuery.of(context).padding.bottom,
              ),
              decoration: BoxDecoration(
                color: bgColor,
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.largeBorderRadius * 2),
                ),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(height: AppSpacing.sm),
                  Container(
                    width: AppSpacing.createEntrySheetHandleWidth,
                    height: AppSpacing.createEntrySheetHandleHeight,
                    decoration: BoxDecoration(
                      color: fgSecondary.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.createEntrySheetHandleHeight / 2,
                      ),
                    ),
                  ),
                  Stack(
                    children: [
                      Padding(
                        padding: EdgeInsets.all(
                          AppSpacing.semantic[DesignSemanticConstants
                                  .container]?[DesignSemanticConstants.md] ??
                              AppSpacing.containerMd,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _buildSectionTitle(
                              context,
                              AppConceptConstants.create,
                              enableCreateActionEntry
                                  ? '先做动作，再决定发成点滴还是作品'
                                  : '回退到旧版创作入口',
                              fgColor,
                            ),
                            SizedBox(height: AppSpacing.sm),
                            enableCreateActionEntry
                                ? _buildActionGrid(context, ref, fgColor)
                                : _buildLegacyGrid(context, ref, fgColor),
                          ],
                        ),
                      ),
                      Positioned(
                        top: 0,
                        right: 0,
                        child: IconButton(
                          onPressed: onClose,
                          icon: const Icon(Icons.close),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionTitle(
    BuildContext context,
    String title,
    String subtitle,
    Color fgColor,
  ) {
    final theme = Theme.of(context).textTheme;
    final baseStyle =
        theme.bodyMedium?.copyWith(color: fgColor) ??
        TextStyle(color: fgColor, fontSize: AppTypography.md);
    return RichText(
      text: TextSpan(
        style: baseStyle,
        children: [
          TextSpan(
            text: title,
            style: baseStyle.copyWith(fontWeight: FontWeight.bold),
          ),
          TextSpan(text: '·$subtitle', style: baseStyle),
        ],
      ),
    );
  }

  Widget _buildActionGrid(BuildContext context, WidgetRef ref, Color fgColor) {
    final items = <_CreateActionCardSpec>[
      _CreateActionCardSpec(
        title: UITextConstants.createActionGallery,
        hint: UITextConstants.createActionGalleryHint,
        onTap: () => onSelect(EditorStartAction.gallery),
        icon: Icons.photo_library_outlined,
        previewImageUrl: _CreateEntryPreviewUrls.gallery,
        key: TestKeys.createActionGallery,
      ),
      _CreateActionCardSpec(
        title: UITextConstants.createActionWrite,
        hint: UITextConstants.createActionWriteHint,
        onTap: () => onSelect(EditorStartAction.write),
        icon: Icons.edit_note_outlined,
        previewImageUrl: _CreateEntryPreviewUrls.write,
        key: TestKeys.createActionWrite,
      ),
      _CreateActionCardSpec(
        title: UITextConstants.createActionCapture,
        hint: UITextConstants.createActionCaptureHint,
        onTap: () => onSelect(EditorStartAction.capture),
        icon: Icons.camera_alt_outlined,
        previewImageUrl: _CreateEntryPreviewUrls.capture,
        key: TestKeys.createActionCapture,
      ),
    ];
    return _buildEntryGrid(context, ref, items, fgColor);
  }

  Widget _buildLegacyGrid(BuildContext context, WidgetRef ref, Color fgColor) {
    final openLegacyTab = onOpenLegacyTab;
    final items = <_CreateActionCardSpec>[
      _CreateActionCardSpec(
        title: UITextConstants.postMoment,
        hint: '直接进入点滴编辑器',
        onTap: () => openLegacyTab?.call('moment'),
        icon: Icons.chat_bubble_outline,
        previewImageUrl: _CreateEntryPreviewUrls.write,
      ),
      _CreateActionCardSpec(
        title: UITextConstants.postPhoto,
        hint: '沿用图片作品入口',
        onTap: () => openLegacyTab?.call('photo'),
        icon: Icons.photo_outlined,
        previewImageUrl: _CreateEntryPreviewUrls.gallery,
      ),
      _CreateActionCardSpec(
        title: UITextConstants.postVideo,
        hint: '沿用视频作品入口',
        onTap: () => openLegacyTab?.call('video'),
        icon: Icons.videocam_outlined,
        previewImageUrl: _CreateEntryPreviewUrls.capture,
      ),
      _CreateActionCardSpec(
        title: UITextConstants.postArticle,
        hint: '沿用笔记编辑入口',
        onTap: () => openLegacyTab?.call('article'),
        icon: Icons.article_outlined,
        previewImageUrl: _CreateEntryPreviewUrls.write,
      ),
    ];
    return _buildEntryGrid(context, ref, items, fgColor);
  }

  Widget _buildEntryGrid(
    BuildContext context,
    WidgetRef ref,
    List<_CreateActionCardSpec> items,
    Color fgColor,
  ) {
    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 3,
      mainAxisSpacing: AppSpacing.sm,
      crossAxisSpacing: AppSpacing.sm,
      childAspectRatio: 0.8,
      children: items.map((item) {
        return _buildEntryCard(
          context: context,
          ref: ref,
          title: item.title,
          hint: item.hint,
          icon: item.icon,
          onTap: item.onTap,
          previewImageUrl: item.previewImageUrl,
          cardKey: item.key,
        );
      }).toList(),
    );
  }

  Widget _buildEntryCard({
    required BuildContext context,
    required WidgetRef ref,
    required String title,
    required String hint,
    required IconData icon,
    required VoidCallback onTap,
    Key? cardKey,
    String? previewImageUrl,
  }) {
    final isDark = ref.watch(isDarkProvider);
    final fgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderSecondary,
    );
    final titleStyle =
        Theme.of(context).textTheme.labelLarge?.copyWith(
          color: fgColor,
          fontWeight: FontWeight.w600,
        ) ??
        TextStyle(color: fgColor, fontWeight: FontWeight.w600);
    final hintStyle =
        Theme.of(context).textTheme.labelSmall?.copyWith(color: fgSecondary) ??
        TextStyle(color: fgSecondary, fontSize: AppTypography.xs);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: cardKey,
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: Container(
          decoration: BoxDecoration(
            border: Border.all(color: borderColor),
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: EdgeInsets.all(AppSpacing.xs + 2),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: titleStyle),
                    Text(hint, style: hintStyle),
                  ],
                ),
              ),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.only(
                    bottomLeft: Radius.circular(
                      AppSpacing.largeBorderRadius - 1,
                    ),
                    bottomRight: Radius.circular(
                      AppSpacing.largeBorderRadius - 1,
                    ),
                  ),
                  child: previewImageUrl != null
                      ? Image.network(
                          previewImageUrl,
                          fit: BoxFit.cover,
                          width: double.infinity,
                          errorBuilder: (_, __, ___) => Icon(
                            icon,
                            size: AppSpacing.iconLarge,
                            color: fgColor,
                          ),
                        )
                      : Icon(icon, size: AppSpacing.iconLarge, color: fgColor),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CreateEntryPreviewUrls {
  static const String gallery =
      'https://images.unsplash.com/photo-1552383276-790b5de4b55b?w=400&fit=crop';
  static const String write =
      'https://images.unsplash.com/photo-1712762056200-50d8f803ba10?w=400&fit=crop';
  static const String capture =
      'https://images.unsplash.com/photo-1726935068680-73cef7e8412b?w=400&fit=crop';
}

class _CreateActionCardSpec {
  const _CreateActionCardSpec({
    required this.title,
    required this.hint,
    required this.onTap,
    required this.icon,
    required this.previewImageUrl,
    this.key,
  });

  final String title;
  final String hint;
  final VoidCallback onTap;
  final IconData icon;
  final String previewImageUrl;
  final Key? key;
}
