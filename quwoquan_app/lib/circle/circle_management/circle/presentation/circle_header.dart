import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/content/media/media_asset/presentation/app_media_image.dart';
import 'package:quwoquan_app/components/object_page/object_page_sections.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 圈子身份头 —— 共享 [ObjectIdentityHeader] 的薄封装。
///
/// 真相源已下沉到 `object_page/object_page_sections.dart` 的身份头底座，与用户主页
/// `ProfileHeader`、实体主页同源 token（`iosTitle3`/`regular` 名称、`iosFootnote` 副标题、
/// 统一上探/留白几何）。此处只把圈子数据映射为：
/// 标题(圈子名) + 圆角方头像([ObjectIdentityKind.circle]) + 类型标签副标题 + 认证勾。
///
/// 简介、统计、成员关系分别由 [ObjectSloganCard] / [ObjectStatsRow] / 成员 Tab 承载，
/// 不再挤在头部（高保 3.3：封面表达圈子氛围，不做成员头像墙）。
class CircleHeader extends StatelessWidget {
  const CircleHeader({
    super.key,
    required this.isDark,
    required this.name,
    this.avatarUrl,
    this.identityTags = const <String>[],
    this.verified = false,
  });

  final bool isDark;
  final String name;
  final String? avatarUrl;

  /// 单行兴趣/类型标签（云侧直出，端以 ` · ` 拼接为副标题；最多 3 个由调用方收口）。
  final List<String> identityTags;

  /// 官方认证标识（蓝勾）。必须来自独立 canonical 认证事实，禁止从生命周期 status 推断。
  final bool verified;

  /// 头像外径（含边框）与上探像素，供 [ObjectPageShell.identityPinExtent] 计算吸顶高度。
  /// 代理共享身份头底座常量，保证四类主页几何一致。
  static double get avatarOuterDiameter =>
      ObjectIdentityHeader.avatarOuterExtentDefault;
  static double get avatarIntrusion =>
      ObjectIdentityHeader.avatarOuterExtentDefault *
      ObjectIdentityHeader.avatarOverlapRatioDefault;

  Widget _buildAvatarFallback(BuildContext context) {
    final initial = name.trim().isEmpty ? '' : name.trim().characters.first;
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final bg = AppColors.iosAccent(context).withValues(alpha: 0.12);
    return ColoredBox(
      color: bg,
      child: Center(
        child: initial.isEmpty
            ? Icon(
                CupertinoIcons.person_3_fill,
                size: AppSpacing.iconMedium,
                color: fg.withValues(alpha: 0.72),
              )
            : Text(
                initial,
                style: TextStyle(
                  fontSize: AppTypography.iosTitle3,
                  fontWeight: AppTypography.semiBold,
                  color: fg,
                ),
              ),
      ),
    );
  }

  Widget? _buildAvatarChild(BuildContext context) {
    final url = (avatarUrl ?? '').trim();
    if (url.isEmpty) {
      return null;
    }
    if (isLocalFileImageSource(url)) {
      return AppMediaImage(
        key: const ValueKey<String>('circle-header-avatar-image'),
        imageSource: url,
        fit: BoxFit.cover,
        errorWidget: _buildAvatarFallback(context),
      );
    }
    return AppMediaImage(
      key: const ValueKey<String>('circle-header-avatar-image'),
      imageSource: url,
      fit: BoxFit.cover,
      errorWidget: _buildAvatarFallback(context),
    );
  }

  @override
  Widget build(BuildContext context) {
    final tags = identityTags
        .map((tag) => tag.trim())
        .where((tag) => tag.isNotEmpty)
        .toList(growable: false);

    return ObjectIdentityHeader(
      title: name,
      media: ObjectIdentityAvatar(
        key: const ValueKey<String>('circle-header-avatar'),
        kind: ObjectIdentityKind.circle,
        child: _buildAvatarChild(context),
      ),
      titleTrailing: verified
          ? Icon(
              key: const ValueKey<String>('circle-header-verified-badge'),
              CupertinoIcons.checkmark_seal_fill,
              size: AppSpacing.iconSmall,
              color: AppColors.iosAccent(context),
            )
          : null,
      subtitle: tags.isNotEmpty ? tags.join(' · ') : null,
    );
  }
}
