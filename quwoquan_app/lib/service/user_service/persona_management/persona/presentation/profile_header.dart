import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/design_system/object_page/object_page_sections.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// Profile header with left-aligned avatar that intrudes 1/3 into the
/// background area above. Display name sits in a Row beside the avatar,
/// aligned to its lower 2/3. No @username is shown.
class ProfileHeader extends StatelessWidget {
  const ProfileHeader({
    super.key,
    required this.isDark,
    this.avatarUrl,
    this.displayName,
    this.identityTags = const <String>[],
    this.verified = false,
    this.onEdit,
    this.showQrCode = false,
    this.onQrCode,
    this.showUploadAvatarPrompt = false,
    this.showIdentityTagPrompt = false,
  });

  final bool isDark;
  final String? avatarUrl;
  final String? displayName;

  /// 主页单行身份标签（云侧 identityTags 直出，端以 · 分隔；与 bio 互补不重复）。
  final List<String> identityTags;

  /// 认证标识（蓝勾）。云侧 verified 直出，端只读展示。
  final bool verified;

  final VoidCallback? onEdit;
  final bool showQrCode;
  final VoidCallback? onQrCode;
  final bool showUploadAvatarPrompt;
  final bool showIdentityTagPrompt;

  static const Key verifiedBadgeKey = ValueKey<String>(
    'profile-header-verified-badge',
  );

  static const double avatarRadius = AppSpacing.xl;
  static const double _avatarBorder = AppSpacing.three;
  static double get avatarOuterDiameter => (avatarRadius + _avatarBorder) * 2;
  static double get avatarOverlapPx =>
      avatarOuterDiameter * UserProfileUIConfig.headerLayout.avatarOverlapRatio;
  static double get avatarIntrusion => avatarOverlapPx;

  Widget _avatarFallback(BuildContext context, Color fgSecondary) {
    return ColoredBox(
      color: AppColors.iosTintedFill(context),
      child: Center(
        child: Icon(
          CupertinoIcons.camera_fill,
          size: AppSpacing.iconLarge,
          color: fgSecondary.withValues(alpha: 0.82),
        ),
      ),
    );
  }

  Widget _buildAvatar(BuildContext context, Color bg, Color fgSecondary) {
    final normalizedAvatarUrl = (avatarUrl ?? '').trim();
    final hasAvatar = normalizedAvatarUrl.isNotEmpty;
    final fallback = _avatarFallback(context, fgSecondary);
    final avatar = Container(
      key: const ValueKey<String>('profile-header-avatar'),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: bg, width: _avatarBorder),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: isDark ? 0.18 : 0.08),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: ClipOval(
        child: SizedBox(
          width: avatarRadius * 2,
          height: avatarRadius * 2,
          child: hasAvatar
              ? (isLocalFileImageSource(normalizedAvatarUrl)
                    ? AppMediaImage(
                        key: const ValueKey<String>(
                          'profile-header-avatar-image',
                        ),
                        imageSource: normalizedAvatarUrl,
                        fit: BoxFit.cover,
                        errorWidget: fallback,
                      )
                    : AppAvatarImage(
                        key: const ValueKey<String>(
                          'profile-header-avatar-image',
                        ),
                        imageUrl: normalizedAvatarUrl,
                        size: avatarRadius * 2,
                        fit: BoxFit.cover,
                        errorWidget: fallback,
                      ))
              : fallback,
        ),
      ),
    );
    if (hasAvatar || !showUploadAvatarPrompt || onEdit == null) {
      return avatar;
    }
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onEdit,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          avatar,
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            ProfileText.profileUploadAvatar,
            style: TextStyle(
              fontSize: AppTypography.iosCaption2,
              color: fgSecondary,
              fontWeight: AppTypography.regular,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bg = SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final tags = identityTags
        .map((tag) => tag.trim())
        .where((tag) => tag.isNotEmpty)
        .toList(growable: false);

    Widget? titleTrailing;
    if (verified) {
      titleTrailing = Icon(
        key: verifiedBadgeKey,
        CupertinoIcons.checkmark_seal_fill,
        size: AppSpacing.iconSmall,
        color: AppColors.iosAccent(context),
      );
    }

    Widget? subtitleOverride;
    if (tags.isEmpty && showIdentityTagPrompt && onEdit != null) {
      subtitleOverride = CupertinoButton(
        key: const ValueKey<String>('profile-header-tags-prompt'),
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onEdit,
        child: Text(
          ProfileText.profileEmptyTagsPrompt,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: fgSecondary,
            fontWeight: AppTypography.regular,
            letterSpacing: -0.08,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      );
    }

    Widget? trailing;
    if (showQrCode && onQrCode != null) {
      trailing = Padding(
        padding: EdgeInsets.only(top: AppSpacing.intraGroupXs),
        child: CupertinoButton(
          key: const ValueKey<String>('profile-header-qr-code'),
          padding: EdgeInsets.zero,
          minimumSize: const Size(
            AppSpacing.appChromeActionButtonSize,
            AppSpacing.appChromeActionButtonSize,
          ),
          onPressed: onQrCode,
          child: SizedBox(
            width: AppSpacing.appChromeActionButtonSize,
            height: AppSpacing.appChromeActionButtonSize,
            child: Center(
              child: Icon(
                CupertinoIcons.qrcode,
                size: AppSpacing.iconMedium,
                color: fg.withValues(alpha: 0.88),
              ),
            ),
          ),
        ),
      );
    }

    return ObjectIdentityHeader(
      title: displayName ?? '',
      media: _buildAvatar(context, bg, fgSecondary),
      titleTrailing: titleTrailing,
      subtitle: tags.isNotEmpty ? tags.join(' · ') : null,
      subtitleOverride: subtitleOverride,
      trailing: trailing,
      avatarOuterExtent: avatarOuterDiameter,
      avatarOverlapRatio: UserProfileUIConfig.headerLayout.avatarOverlapRatio,
    );
  }
}
