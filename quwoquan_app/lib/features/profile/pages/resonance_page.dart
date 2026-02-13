// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 我的交集页（1:1 对应 ResonanceDashboard.tsx）
/// 路由：/profile/resonance
class ResonancePage extends ConsumerStatefulWidget {
  const ResonancePage({super.key});

  @override
  ConsumerState<ResonancePage> createState() => _ResonancePageState();
}

class _ResonancePageState extends ConsumerState<ResonancePage>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

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
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    return Scaffold(
      backgroundColor: bg,
      appBar: AppBar(
        backgroundColor: bg,
        foregroundColor: fg,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
        title: Text(
          UITextConstants.myResonance,
          style: TextStyle(
            color: fg,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        bottom: TabBar(
          controller: _tabController,
          labelColor: fg,
          unselectedLabelColor: fgSecondary,
          indicatorColor: AppColors.primaryColor,
          tabs: const [
            Tab(text: '推荐'),
            Tab(text: '交集'),
            Tab(text: '趣友'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildRecommendTab(fg, fgSecondary),
          _buildIntersectionTab(fg, fgSecondary),
          _buildQuyouTab(fg, fgSecondary),
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
            fontSize: 16,
            fontWeight: FontWeight.w800,
            color: fg,
          ),
        ),
        SizedBox(height: 12),
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
                SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        u['name'] as String,
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          color: fg,
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        u['bio'] as String,
                        style: TextStyle(
                          fontSize: 12,
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
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    '${u['points']} 个交集',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: AppColors.primaryColor,
                    ),
                  ),
                ),
                SizedBox(width: 8),
                TextButton(
                  onPressed: () {},
                  style: TextButton.styleFrom(
                    backgroundColor: AppColors.primaryColor.withValues(alpha: 0.12),
                    foregroundColor: AppColors.primaryColor,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  ),
                  child: Text(UITextConstants.follow),
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
          Icon(Icons.people_outline, size: 64, color: fgSecondary),
          SizedBox(height: 16),
          Text(
            '交集维度：圈子、作者、生活',
            style: TextStyle(color: fgSecondary, fontSize: 14),
          ),
        ],
      ),
    );
  }

  Widget _buildQuyouTab(Color fg, Color fgSecondary) {
    return Center(
      child: Text(
        '趣友列表',
        style: TextStyle(color: fgSecondary, fontSize: 14),
      ),
    );
  }
}
