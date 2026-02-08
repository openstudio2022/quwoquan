import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 创作入口类型
enum CreateEntryType {
  weiquPhoto,
  weiquText,
  weiquVideo,
  zuopinImage,
  zuopinArticle,
  zuopinVideo,
}

/// 创作入口抽屉
///
/// 微趣（照片/文字/视频）+ 作品（图片/文章/视频）六入口。
/// 与原型 CreateEntrySheet 一致。
class CreateEntrySheet extends ConsumerWidget {
  const CreateEntrySheet({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.onSelect,
  });

  final bool isOpen;
  final VoidCallback onClose;
  final void Function(CreateEntryType type) onSelect;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!isOpen) return const SizedBox.shrink();

    final isDark = ref.watch(isDarkProvider);
    final bgColor =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fgColor =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    return Material(
      color: Colors.transparent,
      child: Stack(
        children: [
          GestureDetector(
            onTap: onClose,
            child: Container(
              color: Colors.black.withValues(alpha: 0.5),
            ),
          ),
          Align(
            alignment: Alignment.bottomCenter,
            child: Container(
              constraints: BoxConstraints(
                maxHeight: MediaQuery.of(context).size.height *
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
                          AppSpacing.semantic[DesignSemanticConstants.container]
                                  ?[DesignSemanticConstants.md] ??
                              AppSpacing.containerMd,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _buildSectionTitle(
                              context,
                              AppConceptConstants.weiqu,
                              AppConceptConstants.weiquSubtitle,
                              fgColor,
                            ),
                            SizedBox(height: AppSpacing.sm),
                            _buildWeiquGrid(context, ref, onSelect, fgColor),
                            SizedBox(height: AppSpacing.lg),
                            _buildSectionTitle(
                              context,
                              AppConceptConstants.zuopin,
                              AppConceptConstants.zuopinSubtitle,
                              fgColor,
                            ),
                            SizedBox(height: AppSpacing.sm),
                            _buildZuopinGrid(context, ref, onSelect, fgColor),
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
    final baseStyle = theme.bodyMedium?.copyWith(color: fgColor) ??
        TextStyle(color: fgColor, fontSize: AppTypography.md);
    return RichText(
      text: TextSpan(
        style: baseStyle,
        children: [
          TextSpan(text: title, style: baseStyle.copyWith(fontWeight: FontWeight.bold)),
          TextSpan(text: '·$subtitle', style: baseStyle),
        ],
      ),
    );
  }

  Widget _buildWeiquGrid(
    BuildContext context,
    WidgetRef ref,
    void Function(CreateEntryType) onSelect,
    Color fgColor,
  ) {
    final items = [
      (AppConceptConstants.weiquPhoto, AppConceptConstants.weiquPhotoHint, CreateEntryType.weiquPhoto, Icons.photo_library, _CreateEntryPreviewUrls.weiquPhoto),
      (AppConceptConstants.weiquText, AppConceptConstants.weiquTextHint, CreateEntryType.weiquText, Icons.text_fields, _CreateEntryPreviewUrls.weiquText),
      (AppConceptConstants.weiquVideo, AppConceptConstants.weiquVideoHint, CreateEntryType.weiquVideo, Icons.videocam, _CreateEntryPreviewUrls.weiquVideo),
    ];
    return _buildEntryGrid(context, ref, items, onSelect, fgColor);
  }

  Widget _buildZuopinGrid(
    BuildContext context,
    WidgetRef ref,
    void Function(CreateEntryType) onSelect,
    Color fgColor,
  ) {
    final items = [
      (AppConceptConstants.zuopinImage, AppConceptConstants.zuopinImageHint, CreateEntryType.zuopinImage, Icons.image, _CreateEntryPreviewUrls.zuopinImage),
      (AppConceptConstants.zuopinArticle, AppConceptConstants.zuopinArticleHint, CreateEntryType.zuopinArticle, Icons.article, _CreateEntryPreviewUrls.zuopinArticle),
      (AppConceptConstants.zuopinVideo, AppConceptConstants.zuopinVideoHint, CreateEntryType.zuopinVideo, Icons.movie, _CreateEntryPreviewUrls.zuopinVideo),
    ];
    return _buildEntryGrid(context, ref, items, onSelect, fgColor);
  }

  Widget _buildEntryGrid(
    BuildContext context,
    WidgetRef ref,
    List<(String, String, CreateEntryType, IconData, String)> items,
    void Function(CreateEntryType) onSelect,
    Color fgColor,
  ) {
    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 3,
      mainAxisSpacing: AppSpacing.sm,
      crossAxisSpacing: AppSpacing.sm,
      childAspectRatio: 0.85,
      children: items.map((item) {
        return _buildEntryCard(
          context: context,
          ref: ref,
          title: item.$1,
          hint: item.$2,
          icon: item.$4,
          onTap: () => onSelect(item.$3),
          previewImageUrl: item.$5,
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
    String? previewImageUrl,
  }) {
    final isDark = ref.watch(isDarkProvider);
    final fgColor =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor =
        AppColorsFunctional.getColor(isDark, ColorType.borderSecondary);
    final titleStyle = Theme.of(context).textTheme.labelLarge?.copyWith(
          color: fgColor,
          fontWeight: FontWeight.w600,
        ) ??
        TextStyle(color: fgColor, fontWeight: FontWeight.w600);
    final hintStyle = Theme.of(context).textTheme.labelSmall?.copyWith(
          color: fgSecondary,
        ) ??
        TextStyle(color: fgSecondary, fontSize: AppTypography.xs);
    return Material(
      color: Colors.transparent,
      child: InkWell(
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
                    bottomLeft: Radius.circular(AppSpacing.largeBorderRadius - 1),
                    bottomRight: Radius.circular(AppSpacing.largeBorderRadius - 1),
                  ),
                  child: previewImageUrl != null
                      ? Image.network(
                          previewImageUrl,
                          fit: BoxFit.cover,
                          width: double.infinity,
                          errorBuilder: (_, __, ___) => Icon(icon, size: AppSpacing.iconLarge, color: fgColor),
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

/// 1:1 来自 CreateEntrySheet.tsx 各按钮预览图 URL
class _CreateEntryPreviewUrls {
  static const String weiquPhoto =
      'https://images.unsplash.com/photo-1552383276-790b5de4b55b?w=400&fit=crop';
  static const String weiquText =
      'https://images.unsplash.com/photo-1712762056200-50d8f803ba10?w=400&fit=crop';
  static const String weiquVideo =
      'https://images.unsplash.com/photo-1726935068680-73cef7e8412b?w=400&fit=crop';
  static const String zuopinImage =
      'https://images.unsplash.com/photo-1759070725320-2bdd608c8eab?w=400&fit=crop';
  static const String zuopinArticle =
      'https://images.unsplash.com/photo-1638342863994-ae4eee256688?w=400&fit=crop';
  static const String zuopinVideo =
      'https://images.unsplash.com/photo-1741836198509-7297c2d8bb24?w=400&fit=crop';
}
