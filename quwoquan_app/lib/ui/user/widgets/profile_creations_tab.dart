import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/creation_visibility_popup.dart';

class ProfileCreationsTab extends ConsumerWidget {
  const ProfileCreationsTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;

  static const _subTabLabels = {
    CreationSubTab.all: '全部',
    CreationSubTab.micro: '微趣',
    CreationSubTab.image: '图片',
    CreationSubTab.video: '视频',
    CreationSubTab.article: '文字',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifier = ref.watch(profileNotifierProvider(userId));
    final state = notifier.state;
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final primary = AppColors.primaryColor;

    return Column(
      children: [
        SizedBox(
          height: AppSpacing.subTabNavigationHeight,
          child: Row(
            children: [
              Expanded(
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
                  children: CreationSubTab.values.map((tab) {
                    final isActive = tab == state.activeSubTab;
                    return GestureDetector(
                      onTap: () => notifier.setSubTab(tab),
                      child: Container(
                        alignment: Alignment.center,
                        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
                        child: Text(
                          _subTabLabels[tab]!,
                          style: TextStyle(
                            fontSize: AppTypography.md,
                            fontWeight: isActive ? AppTypography.semiBold : AppTypography.normal,
                            color: isActive ? primary : fgSecondary,
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ),
            ],
          ),
        ),
        if (state.activeVisibility != CreationVisibility.all)
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerMd,
              vertical: AppSpacing.intraGroupSm,
            ),
            child: CreationVisibilityPopup(
              mode: mode,
              current: state.activeVisibility,
              isDark: isDark,
              onSelected: notifier.setVisibility,
            ),
          ),
        Expanded(
          child: _buildCreationsGrid(state, fg, fgSecondary),
        ),
      ],
    );
  }

  String _coverUrlForPost(PostBaseDto post) {
    final map = post.toMap();
    return (map['coverUrl'] ?? map['thumbnailUrl'] ?? map['imageUrls']?[0] ?? '').toString();
  }

  Widget _buildCreationsGrid(ProfileState state, Color fg, Color fgSecondary) {
    final items = state.creations.where((p) {
      if (state.activeSubTab != CreationSubTab.all) {
        final typeMap = {
          CreationSubTab.micro: 'moment',
          CreationSubTab.image: 'photo',
          CreationSubTab.video: 'video',
          CreationSubTab.article: 'article',
        };
        if (p.type != typeMap[state.activeSubTab]) return false;
      }
      return true;
    }).toList();

    if (items.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.photo_library_outlined, size: AppSpacing.xl * 2, color: fgSecondary),
            SizedBox(height: AppSpacing.md),
            Text(
              mode == ProfileMode.mine ? '还没有创作内容' : 'Ta 还没有创作内容',
              style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
            ),
          ],
        ),
      );
    }

    return GridView.builder(
      padding: EdgeInsets.all(AppSpacing.containerSm),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: AppSpacing.sm,
        crossAxisSpacing: AppSpacing.sm,
        childAspectRatio: 0.8,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final post = items[index];
        final cover = _coverUrlForPost(post);
        final isPrivate = state.activeVisibility == CreationVisibility.private_;
        return ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (cover.isNotEmpty)
                Image.network(
                  cover,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => Container(
                    color: fgSecondary.withValues(alpha: 0.1),
                    child: Icon(Icons.image, color: fgSecondary),
                  ),
                )
              else
                Container(
                  color: fgSecondary.withValues(alpha: 0.1),
                  child: Icon(Icons.image, color: fgSecondary),
                ),
              if (isPrivate)
                Container(
                  color: Colors.black.withValues(alpha: 0.3),
                  child: Center(
                    child: Icon(
                      Icons.lock_outline,
                      color: Colors.white.withValues(alpha: 0.8),
                      size: AppSpacing.iconMedium,
                    ),
                  ),
                ),
              Positioned(
                bottom: 0,
                left: 0,
                right: 0,
                child: Container(
                  padding: EdgeInsets.all(AppSpacing.intraGroupMd),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.bottomCenter,
                      end: Alignment.topCenter,
                      colors: [
                        Colors.black.withValues(alpha: 0.6),
                        Colors.transparent,
                      ],
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.favorite, size: AppTypography.sm, color: Colors.white),
                      SizedBox(width: AppSpacing.intraGroupXs),
                      Text(
                        '${post.likeCount}',
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          fontWeight: AppTypography.medium,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
