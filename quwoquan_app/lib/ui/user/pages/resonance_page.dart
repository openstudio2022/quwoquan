// ignore_for_file: unnecessary_underscores, deprecated_member_use

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

/// 我的交集页（1:1 对应 ResonanceDashboard.tsx）
/// 路由：/profile/resonance
class ResonancePage extends ConsumerStatefulWidget {
  const ResonancePage({super.key});

  @override
  ConsumerState<ResonancePage> createState() => _ResonancePageState();
}

class _ResonancePageState extends ConsumerState<ResonancePage> {
  late PageController _pageController;
  int _currentIndex = 0;

  /// 1:1 ResonanceDashboard 推荐趣友
  static const List<Map<String, dynamic>> _resonantFriends = [
    {
      'id': 'u1',
      'name': '陈摄影师',
      'avatar':
          'https://images.unsplash.com/photo-1603987248955-9c142c5ae89b?q=80&w=150',
      'points': 12,
      'bio': '徕卡玩家 / 极简主义者',
    },
    {
      'id': 'u2',
      'name': '阿强',
      'avatar':
          'https://images.unsplash.com/photo-1755519024555-a660fefc8dc3?q=80&w=150',
      'points': 9,
      'bio': '阿那亚常客 / 自由撰稿人',
    },
    {
      'id': 'u3',
      'name': 'Sarah',
      'avatar':
          'https://images.unsplash.com/photo-1643816831234-e7cb32194e92?q=80&w=150',
      'points': 8,
      'bio': '胶片摄影爱好者',
    },
  ];

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: bg,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.back),
          onPressed: () => context.pop(),
        ),
        middle: Text(
          UITextConstants.myResonance,
          style: TextStyle(
            color: fg,
            fontSize: AppTypography.xl,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: CupertinoSlidingSegmentedControl<int>(
              groupValue: _currentIndex,
              children: const {
                0: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 20),
                    child: Text('推荐')),
                1: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 20),
                    child: Text('交集')),
                2: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 20),
                    child: Text('趣友')),
              },
              onValueChanged: (index) {
                if (index != null) {
                  setState(() => _currentIndex = index);
                  _pageController.animateToPage(
                    index,
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeInOut,
                  );
                }
              },
            ),
          ),
          Expanded(
            child: PageView(
              controller: _pageController,
              physics: const BouncingScrollPhysics(),
              onPageChanged: (index) => setState(() => _currentIndex = index),
              children: [
                _buildRecommendTab(fg, fgSecondary),
                _buildIntersectionTab(fg, fgSecondary),
                _buildQuyouTab(fg, fgSecondary),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecommendTab(Color fg, Color fgSecondary) {
    return ListView(
      padding: EdgeInsets.all(
        AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ?? AppSpacing.containerMd,
      ),
      children: [
        Text(
          '与你有交集的趣友',
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: FontWeight.w800,
            color: fg,
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupLg),
        ..._resonantFriends.map((u) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 28,
                  backgroundImage: NetworkImage(u['avatar'] as String),
                  onBackgroundImageError: (_, __) {},
                ),
                SizedBox(width: AppSpacing.intraGroupLg),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        u['name'] as String,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: FontWeight.w800,
                          color: fg,
                        ),
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        u['bio'] as String,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.primaryColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
                  ),
                  child: Text(
                    '${u['points']} 个交集',
                    style: TextStyle(
                      fontSize: AppTypography.xsPlus,
                      fontWeight: FontWeight.w700,
                      color: AppColors.primaryColor,
                    ),
                  ),
                ),
                SizedBox(width: AppSpacing.sm),
                CupertinoButton(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  color: AppColors.primaryColor.withValues(alpha: 0.12),
                  minSize: 0,
                  borderRadius: BorderRadius.circular(AppSpacing.eighteen),
                  onPressed: () {},
                  child: Text(
                    UITextConstants.follow,
                    style: TextStyle(
                      color: AppColors.primaryColor,
                      fontSize: AppTypography.base,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          );
        }),
      ],
    );
  }

  Widget _buildIntersectionTab(Color fg, Color fgSecondary) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(CupertinoIcons.person_2, size: AppSpacing.largeAvatarSize, color: fgSecondary),
          SizedBox(height: AppSpacing.md),
          Text(
            '交集维度：圈子、作者、生活',
            style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
          ),
        ],
      ),
    );
  }

  Widget _buildQuyouTab(Color fg, Color fgSecondary) {
    return Center(
      child: Text(
        '趣友列表',
        style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
      ),
    );
  }
}
