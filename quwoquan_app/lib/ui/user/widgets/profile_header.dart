import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

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
    this.showEdit = false,
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

  /// 我的主页昵称右侧编辑入口。
  final bool showEdit;
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

  Widget _buildAvatar(BuildContext context, Color bg, Color fgSecondary) {
    // 本地选取（未上传）路径原样交给 FileImage；服务端对象键 / 远端地址走解析器。
    final resolvedAvatarUrl = isLocalFileImageSource(avatarUrl)
        ? (avatarUrl ?? '')
        : resolveAvatarImageUrl(avatarUrl);
    final hasAvatar = resolvedAvatarUrl.isNotEmpty;
    final avatarImage = hasAvatar
        ? mediaImageProvider(resolvedAvatarUrl)
        : null;
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
      child: hasAvatar && avatarImage != null
          ? CircleAvatar(
              radius: avatarRadius,
              backgroundColor: AppColors.iosSecondaryFill(context),
              backgroundImage: avatarImage,
              onBackgroundImageError: (e, s) {},
            )
          : CircleAvatar(
              radius: avatarRadius,
              backgroundColor: AppColors.iosTintedFill(context),
              child: Icon(
                CupertinoIcons.camera_fill,
                size: AppSpacing.iconLarge,
                color: fgSecondary.withValues(alpha: 0.82),
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
            UITextConstants.profileUploadAvatar,
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

    return Stack(
      clipBehavior: Clip.none,
      children: [
        Padding(
          padding: EdgeInsets.only(left: avatarOuterDiameter + AppSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(height: AppSpacing.intraGroupXs),
              Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Flexible(
                    child: Text(
                      displayName ?? '',
                      style: TextStyle(
                        fontSize: AppTypography.iosTitle3,
                        fontWeight: AppTypography.regular,
                        color: fg.withValues(alpha: 0.94),
                        letterSpacing: -0.24,
                        height: AppSpacing.textLineHeightDense,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (verified) ...[
                    SizedBox(width: AppSpacing.intraGroupXs),
                    Icon(
                      key: verifiedBadgeKey,
                      CupertinoIcons.checkmark_seal_fill,
                      size: AppSpacing.iconSmall,
                      color: AppColors.iosAccent(context),
                    ),
                  ],
                  if (showQrCode && onQrCode != null) ...[
                    SizedBox(width: AppSpacing.intraGroupXs),
                    CupertinoButton(
                      key: const ValueKey<String>('profile-header-qr-code'),
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.intraGroupXs,
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      minimumSize: const Size(
                        AppSpacing.buttonHeightSm,
                        AppSpacing.buttonHeightSm,
                      ),
                      onPressed: onQrCode,
                      child: Icon(
                        CupertinoIcons.qrcode,
                        size: AppSpacing.iconMedium,
                        color: fg.withValues(alpha: 0.88),
                      ),
                    ),
                  ],
                  if (showEdit && onEdit != null) ...[
                    SizedBox(width: AppSpacing.intraGroupXs),
                    CupertinoButton(
                      key: const ValueKey<String>('profile-header-edit'),
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.intraGroupXs,
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      minimumSize: const Size(
                        AppSpacing.buttonHeightSm,
                        AppSpacing.buttonHeightSm,
                      ),
                      onPressed: onEdit,
                      child: Icon(
                        CupertinoIcons.square_pencil,
                        size: AppSpacing.iconMedium,
                        color: fg.withValues(alpha: 0.88),
                      ),
                    ),
                  ],
                ],
              ),
              if (tags.isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  key: const ValueKey<String>('profile-header-identity-tags'),
                  tags.join(' · '),
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: fgSecondary,
                    letterSpacing: -0.08,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ] else if (showIdentityTagPrompt && onEdit != null) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                CupertinoButton(
                  key: const ValueKey<String>('profile-header-tags-prompt'),
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: onEdit,
                  child: Text(
                    UITextConstants.profileEmptyTagsPrompt,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: fgSecondary,
                      fontWeight: AppTypography.regular,
                      letterSpacing: -0.08,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ],
          ),
        ),
        Positioned(
          top: -avatarOverlapPx,
          left: 0,
          child: _buildAvatar(context, bg, fgSecondary),
        ),
      ],
    );
  }
}
