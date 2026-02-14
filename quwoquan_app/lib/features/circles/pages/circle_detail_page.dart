// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 圈子主页
///
/// 1:1 复制自 趣我圈2026/src CirclePageV2.tsx
/// initialRole: owner | admin | member | visitor；joinStatus: none | pending | joined
/// 3-Tab 创作/互动/生活、子分类、网格/列表、统计弹层、编辑圈子/管理中心/更多菜单
enum CircleRole { owner, admin, member, visitor }

class CircleDetailPage extends ConsumerStatefulWidget {
  final String circleId;
  final VoidCallback onBack;
  final CircleRole initialRole;

  const CircleDetailPage({
    super.key,
    required this.circleId,
    required this.onBack,
    this.initialRole = CircleRole.visitor,
  });

  @override
  ConsumerState<CircleDetailPage> createState() => _CircleDetailPageState();
}

class _CircleDetailPageState extends ConsumerState<CircleDetailPage> {
  late CircleRole _role;
  String _activeTab = 'works';
  String _activeSubTab = 'all';
  String _joinStatus = 'none'; // none | pending | joined
  bool _isJoined = false;
  bool _isFollowed = false;
  final String _admissionRule = 'approval'; // open | approval | invite
  bool _showEditModal = false;
  bool _showManageModal = false;
  bool _showMoreMenu = false;
  bool _worksViewModeGrid = true;
  bool _lifestyleViewModeGrid = true;

  Map<String, dynamic> get _circleInfo {
    final info = ref.read(appContentRepositoryProvider).circlePageCircleInfo;
    return {...info, 'id': widget.circleId};
  }

  @override
  void initState() {
    super.initState();
    _role = widget.initialRole;
    _isJoined = _role == CircleRole.member || _role == CircleRole.owner || _role == CircleRole.admin;
    _isFollowed = _isJoined;
    _joinStatus = _isJoined ? 'joined' : 'none';
    if (_activeTab == 'works') _activeSubTab = 'all';
    if (_activeTab == 'interaction') _activeSubTab = 'likes';
    if (_activeTab == 'lifestyle') _activeSubTab = 'all';
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        ref.read(visitRecorderServiceProvider).recordVisit(
              VisitTarget.entity(kind: VisitEntityKind.circle, id: widget.circleId),
            );
      }
    });
  }

  void _handleJoinCircle() {
    if (_joinStatus != 'none') return;
    if (_admissionRule == 'approval') {
      setState(() => _joinStatus = 'pending');
    } else {
      setState(() {
        _joinStatus = 'joined';
        _isJoined = true;
        _isFollowed = true;
      });
    }
  }

  void _handleFollow() {
    setState(() => _isFollowed = !_isFollowed);
  }

  Widget _buildActionButtons(bool isDark, Color fgSecondary) {
    final containerMd = AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ?? AppSpacing.containerMd;
    if (_role == CircleRole.owner || _role == CircleRole.admin) {
      return Padding(
        padding: EdgeInsets.only(top: containerMd),
        child: Row(
          children: [
            _ActionButton(
              label: UITextConstants.editCircle,
              onTap: () => setState(() => _showEditModal = true),
              isDark: isDark,
            ),
            SizedBox(width: AppSpacing.sm),
            _ActionButton(
              label: UITextConstants.manageCenter,
              onTap: () => setState(() => _showManageModal = true),
              isDark: isDark,
            ),
          ],
        ),
      );
    }
    final isPending = _joinStatus == 'pending';
    final isActuallyJoined = _joinStatus == 'joined';
    final shouldShowJoin = _admissionRule != 'invite' || isActuallyJoined;
    return Padding(
      padding: EdgeInsets.only(top: containerMd),
      child: Row(
        children: [
          _ActionButton(
            label: _isFollowed ? UITextConstants.followedCircle : UITextConstants.followCircle,
            onTap: _handleFollow,
            isSecondary: true,
            isDark: isDark,
          ),
          if (shouldShowJoin) ...[
            SizedBox(width: AppSpacing.sm),
            _ActionButton(
              label: isActuallyJoined ? UITextConstants.joinedCircle : isPending ? UITextConstants.joinPending : UITextConstants.joinCircle,
              onTap: _handleJoinCircle,
              isPrimary: !isActuallyJoined && !isPending,
              isPending: isPending,
              isDark: isDark,
            ),
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fgPrimary = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    final topPadding = MediaQuery.of(context).padding.top;

    return Scaffold(
      backgroundColor: bgColor,
      body: Stack(
        children: [
          CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: Stack(
                  children: [
                    SizedBox(
                      height: 320,
                      width: double.infinity,
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          Image.network(
                            _circleInfo['cover'] as String,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => Container(color: fgSecondary.withValues(alpha: 0.2)),
                          ),
                          Container(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [Colors.black.withValues(alpha: 0.4), Colors.transparent],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    Positioned(
                      top: topPadding + 8,
                      left: AppSpacing.sm,
                      child: Material(
                        color: Colors.black.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(24),
                        child: InkWell(
                          onTap: widget.onBack,
                          borderRadius: BorderRadius.circular(24),
                          child: Padding(
                            padding: EdgeInsets.all(AppSpacing.sm),
                            child: Icon(Icons.arrow_back, color: Colors.white, size: 24),
                          ),
                        ),
                      ),
                    ),
                    Positioned(
                      top: topPadding + 8,
                      right: AppSpacing.sm,
                      child: Material(
                        color: Colors.black.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(24),
                        child: InkWell(
                          onTap: () => setState(() => _showMoreMenu = true),
                          borderRadius: BorderRadius.circular(24),
                          child: Padding(
                            padding: EdgeInsets.all(AppSpacing.sm),
                            child: Icon(Icons.more_horiz, color: Colors.white, size: 24),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              SliverToBoxAdapter(
                child: Transform.translate(
                  offset: const Offset(0, -96),
                  child: Container(
                    margin: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                    padding: EdgeInsets.all(AppSpacing.lg),
                    decoration: BoxDecoration(
                      color: bgColor,
                      borderRadius: BorderRadius.circular(56),
                      border: Border.all(color: borderColor),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.08),
                          blurRadius: 24,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Transform.translate(
                              offset: const Offset(0, -80),
                              child: Stack(
                                clipBehavior: Clip.none,
                                children: [
                                  Container(
                                    width: 128,
                                    height: 128,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      border: Border.all(color: bgColor, width: 6),
                                      boxShadow: [
                                        BoxShadow(
                                          color: Colors.black.withValues(alpha: 0.15),
                                          blurRadius: 16,
                                          offset: const Offset(0, 4),
                                        ),
                                      ],
                                    ),
                                    child: ClipOval(
                                      child: Image.network(
                                        _circleInfo['avatar'] as String,
                                        fit: BoxFit.cover,
                                        errorBuilder: (_, __, ___) => Icon(Icons.group, size: 48, color: fgSecondary),
                                      ),
                                    ),
                                  ),
                                  Positioned(
                                    bottom: 8,
                                    right: 8,
                                    child: Container(
                                      padding: EdgeInsets.all(8),
                                      decoration: BoxDecoration(
                                        color: AppColors.primaryColor,
                                        shape: BoxShape.circle,
                                        border: Border.all(color: bgColor, width: 4),
                                      ),
                                      child: Icon(Icons.verified, color: Colors.white, size: 16),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            _buildActionButtons(isDark, fgSecondary),
                          ],
                        ),
                        SizedBox(height: AppSpacing.md),
                        Text(
                          _circleInfo['name'] as String,
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w900,
                            color: fgPrimary,
                          ),
                        ),
                        SizedBox(height: 6),
                        Text(
                          '${_circleInfo['desc']}\n${UITextConstants.circleOfficialBadge}',
                          style: TextStyle(
                            fontSize: 14,
                            color: fgSecondary,
                            height: 1.4,
                          ),
                        ),
                        Padding(
                          padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
                          child: Row(
                            children: [
                              _StatChip(
                                value: (_circleInfo['stats'] as Map)['members'] as String,
                                label: UITextConstants.circleMembers,
                                hasDot: _circleInfo['hasNewMessages'] == true,
                                onTap: () => context.push('/circle/${widget.circleId}/stats?type=members'),
                                isDark: isDark,
                                fgPrimary: fgPrimary,
                                fgSecondary: fgSecondary,
                              ),
                              Container(width: 1, height: 24, color: borderColor),
                              _StatChip(
                                value: (_circleInfo['stats'] as Map)['groups'] as String,
                                label: UITextConstants.circleGroups,
                                hasDot: _circleInfo['hasNewMessages'] == true,
                                onTap: () => context.push('/circle/${widget.circleId}/stats?type=groups'),
                                isDark: isDark,
                                fgPrimary: fgPrimary,
                                fgSecondary: fgSecondary,
                              ),
                              Container(width: 1, height: 24, color: borderColor),
                              _StatChip(
                                value: (_circleInfo['stats'] as Map)['fans'] as String,
                                label: UITextConstants.circleFans,
                                onTap: () => context.push('/circle/${widget.circleId}/stats?type=fans'),
                                isDark: isDark,
                                fgPrimary: fgPrimary,
                                fgSecondary: fgSecondary,
                              ),
                              Container(width: 1, height: 24, color: borderColor),
                              _StatChip(
                                value: (_circleInfo['stats'] as Map)['likes'] as String,
                                label: UITextConstants.circleLikes,
                                onTap: () => context.push('/circle/${widget.circleId}/stats?type=likes'),
                                isDark: isDark,
                                fgPrimary: fgPrimary,
                                fgSecondary: fgSecondary,
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Container(
                  margin: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                  decoration: BoxDecoration(
                    color: bgColor,
                    borderRadius: BorderRadius.only(topLeft: Radius.circular(48), topRight: Radius.circular(48)),
                    border: Border.all(color: borderColor),
                  ),
                  child: Column(
                    children: [
                      _buildTabBar(fgPrimary, fgSecondary),
                      _buildTabContent(isDark, fgPrimary, fgSecondary),
                    ],
                  ),
                ),
              ),
            ],
          ),
          if (_showEditModal) _buildEditModalPlaceholder(isDark),
          if (_showManageModal) _buildManageModalPlaceholder(isDark),
          if (_showMoreMenu) _buildMoreMenu(isDark, fgSecondary),
        ],
      ),
    );
  }

  Widget _buildTabBar(Color fgPrimary, Color fgSecondary) {
    final tabs = [
      UITextConstants.circleWorksTab,
      UITextConstants.circleInteractionTab,
      UITextConstants.circleLifestyleTab,
    ];
    final ids = ['works', 'interaction', 'lifestyle'];
    return Row(
      children: List.generate(3, (i) {
        final selected = _activeTab == ids[i];
        return Expanded(
          child: InkWell(
            onTap: () {
              setState(() {
                _activeTab = ids[i];
                _activeSubTab = ids[i] == 'works' ? 'all' : ids[i] == 'interaction' ? 'likes' : 'all';
              });
            },
            child: Container(
              padding: EdgeInsets.symmetric(vertical: 16),
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: selected ? AppColors.primaryColor : Colors.transparent,
                    width: 3,
                  ),
                ),
              ),
              child: Text(
                tabs[i],
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  color: selected ? fgPrimary : fgSecondary,
                ),
              ),
            ),
          ),
        );
      }),
    );
  }

  Widget _buildTabContent(bool isDark, Color fgPrimary, Color fgSecondary) {
    if (_activeTab == 'works') {
      return _buildWorksTab(isDark, fgPrimary, fgSecondary);
    }
    if (_activeTab == 'interaction') {
      return _buildInteractionTab(isDark, fgSecondary);
    }
    return _buildLifestyleTab(isDark, fgPrimary, fgSecondary);
  }

  Widget _buildWorksTab(bool isDark, Color fgPrimary, Color fgSecondary) {
    final subs = [UITextConstants.circleSubAll, UITextConstants.circleSubPhoto, UITextConstants.circleSubVideo, UITextConstants.circleSubArticle];
    final subIds = ['all', 'photo', 'video', 'article'];
    return Padding(
      padding: EdgeInsets.all(AppSpacing.md),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: List.generate(4, (i) {
                      final selected = _activeSubTab == subIds[i];
                      return Padding(
                        padding: EdgeInsets.only(right: AppSpacing.sm),
                        child: GestureDetector(
                          onTap: () => setState(() => _activeSubTab = subIds[i]),
                          child: Container(
                            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                            decoration: BoxDecoration(
                              color: selected ? (isDark ? Colors.white.withValues(alpha: 0.1) : Colors.black.withValues(alpha: 0.06)) : null,
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(color: isDark ? Colors.white24 : Colors.black12),
                            ),
                            child: Text(subs[i], style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: selected ? fgPrimary : fgSecondary)),
                          ),
                        ),
                      );
                    }),
                  ),
                ),
              ),
              IconButton(
                icon: Icon(_worksViewModeGrid ? Icons.view_list : Icons.grid_view, color: fgSecondary),
                onPressed: () => setState(() => _worksViewModeGrid = !_worksViewModeGrid),
              ),
            ],
          ),
          SizedBox(height: 16),
          if (_worksViewModeGrid)
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                mainAxisSpacing: 8,
                crossAxisSpacing: 8,
                childAspectRatio: 1,
              ),
              itemCount: 10,
              itemBuilder: (_, i) => ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.network(
                  'https://images.unsplash.com/photo-${1600000000000 + i * 1111}?q=80&w=400',
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => Container(color: fgSecondary.withValues(alpha: 0.2)),
                ),
              ),
            )
          else
            Column(
              children: List.generate(5, (i) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.sm),
                child: Container(
                  padding: EdgeInsets.all(AppSpacing.sm),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.03),
                    borderRadius: BorderRadius.circular(32),
                    border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(16),
                        child: Image.network(
                          'https://images.unsplash.com/photo-${1600000000000 + i * 2222}?q=80&w=800',
                          height: 120,
                          width: double.infinity,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(height: 120, color: fgSecondary.withValues(alpha: 0.2)),
                        ),
                      ),
                      SizedBox(height: 8),
                      Text('作品标题示例 ${i + 1}', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: fgPrimary)),
                      Text('2024.02.01 · ${120 + i * 10} 获赞', style: TextStyle(fontSize: 11, color: fgSecondary)),
                    ],
                  ),
                ),
              )),
            ),
        ],
      ),
    );
  }

  Widget _buildInteractionTab(bool isDark, Color fgSecondary) {
    final subs = [UITextConstants.circleSubLikes, UITextConstants.circleSubComments];
    final subIds = ['likes', 'comments'];
    return Padding(
      padding: EdgeInsets.all(AppSpacing.md),
      child: Column(
        children: [
          Row(
            children: List.generate(2, (i) {
              final selected = _activeSubTab == subIds[i];
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.sm),
                child: GestureDetector(
                  onTap: () => setState(() => _activeSubTab = subIds[i]),
                  child: Container(
                    padding: EdgeInsets.symmetric(horizontal: 24, vertical: 8),
                    decoration: BoxDecoration(
                      color: selected ? (isDark ? Colors.white.withValues(alpha: 0.1) : Colors.black.withValues(alpha: 0.06)) : null,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: isDark ? Colors.white24 : Colors.black12),
                    ),
                    child: Text(subs[i], style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: fgSecondary)),
                  ),
                ),
              );
            }),
          ),
          SizedBox(height: 16),
          Text('互动列表占位（InteractionItem 1:1 待接入）', style: TextStyle(fontSize: 13, color: fgSecondary)),
        ],
      ),
    );
  }

  Widget _buildLifestyleTab(bool isDark, Color fgPrimary, Color fgSecondary) {
    final subs = [AppConceptConstants.all, AppConceptConstants.footprint, AppConceptConstants.bookMovieMusic, AppConceptConstants.taste, AppConceptConstants.aiwu];
    final subIds = ['all', 'footprint', 'soul', 'taste', 'private'];
    return Padding(
      padding: EdgeInsets.all(AppSpacing.md),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: List.generate(5, (i) {
                      final selected = _activeSubTab == subIds[i];
                      return Padding(
                        padding: EdgeInsets.only(right: AppSpacing.sm),
                        child: GestureDetector(
                          onTap: () => setState(() => _activeSubTab = subIds[i]),
                          child: Container(
                            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: selected ? (isDark ? Colors.white.withValues(alpha: 0.1) : Colors.black.withValues(alpha: 0.06)) : null,
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(color: isDark ? Colors.white24 : Colors.black12),
                            ),
                            child: Text(subs[i], style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: selected ? fgPrimary : fgSecondary)),
                          ),
                        ),
                      );
                    }),
                  ),
                ),
              ),
              IconButton(
                icon: Icon(_lifestyleViewModeGrid ? Icons.view_list : Icons.grid_view, color: fgSecondary),
                onPressed: () => setState(() => _lifestyleViewModeGrid = !_lifestyleViewModeGrid),
              ),
            ],
          ),
          SizedBox(height: 16),
          if (_lifestyleViewModeGrid)
            GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                mainAxisSpacing: 8,
                crossAxisSpacing: 8,
                childAspectRatio: 1,
              ),
              itemCount: 6,
              itemBuilder: (_, i) => Stack(
                fit: StackFit.expand,
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: Image.network(
                      'https://images.unsplash.com/photo-${1610000000000 + i * 2222}?q=80&w=400',
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Container(color: fgSecondary.withValues(alpha: 0.2)),
                    ),
                  ),
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    child: Container(
                      padding: EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Colors.transparent, Colors.black54]),
                        borderRadius: BorderRadius.only(bottomLeft: Radius.circular(12), bottomRight: Radius.circular(12)),
                      ),
                      child: Text('社员微趣 ${i + 1}', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: Colors.white)),
                    ),
                  ),
                ],
              ),
            )
          else
            Column(
              children: List.generate(4, (i) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.sm),
                child: Container(
                  padding: EdgeInsets.all(AppSpacing.sm),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.03),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
                  ),
                  child: Row(
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(16),
                        child: Image.network(
                          'https://images.unsplash.com/photo-${1610000000000 + i * 3333}?q=80&w=400',
                          width: 96,
                          height: 96,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(width: 96, height: 96, color: fgSecondary.withValues(alpha: 0.2)),
                        ),
                      ),
                      SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('生活点滴示例 ${i + 1}', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: fgPrimary)),
                            Text('记录这一刻的美好生活...', style: TextStyle(fontSize: 11, color: fgSecondary), maxLines: 2, overflow: TextOverflow.ellipsis),
                            SizedBox(height: 4),
                            Text('# 摄影生活 # 微趣记录', style: TextStyle(fontSize: 10, color: AppColors.primaryColor, fontWeight: FontWeight.w800)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              )),
            ),
        ],
      ),
    );
  }

  Widget _buildEditModalPlaceholder(bool isDark) {
    return Material(
      color: Colors.black54,
      child: Center(
        child: Container(
          margin: EdgeInsets.all(24),
          padding: EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
            borderRadius: BorderRadius.circular(24),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(UITextConstants.editCircle),
              SizedBox(height: 16),
              TextButton(onPressed: () => setState(() => _showEditModal = false), child: Text(UITextConstants.cancel)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildManageModalPlaceholder(bool isDark) {
    return Material(
      color: Colors.black54,
      child: Center(
        child: Container(
          margin: EdgeInsets.all(24),
          padding: EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
            borderRadius: BorderRadius.circular(24),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(UITextConstants.manageCenter),
              SizedBox(height: 16),
              TextButton(onPressed: () => setState(() => _showManageModal = false), child: Text(UITextConstants.cancel)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMoreMenu(bool isDark, Color fgSecondary) {
    return Stack(
      children: [
        GestureDetector(
          onTap: () => setState(() => _showMoreMenu = false),
          child: Container(color: Colors.black54),
        ),
        Align(
          alignment: Alignment.bottomCenter,
          child: Container(
            padding: EdgeInsets.only(top: 24, left: 24, right: 24, bottom: MediaQuery.of(context).padding.bottom + 24),
            decoration: BoxDecoration(
              color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
              borderRadius: BorderRadius.vertical(top: Radius.circular(40)),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(width: 48, height: 4, decoration: BoxDecoration(color: fgSecondary.withValues(alpha: 0.3), borderRadius: BorderRadius.circular(2))),
                SizedBox(height: 24),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    _MoreMenuItem(icon: Icons.share, label: '分享圈子', color: AppColors.primaryColor),
                    _MoreMenuItem(icon: Icons.save, label: '保存封面', color: AppColors.success),
                    _MoreMenuItem(icon: Icons.report, label: '举报圈子', color: Colors.orange),
                    _MoreMenuItem(icon: _isJoined ? Icons.logout : Icons.settings, label: _isJoined ? '退出圈子' : '设置', color: Colors.red),
                  ],
                ),
                SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: TextButton(
                    onPressed: () => setState(() => _showMoreMenu = false),
                    child: Text(UITextConstants.cancel),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _ActionButton extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  final bool isPrimary;
  final bool isSecondary;
  final bool isPending;
  final bool isDark;

  const _ActionButton({
    required this.label,
    required this.onTap,
    required this.isDark,
    this.isPrimary = false,
    this.isSecondary = false,
    this.isPending = false,
  });

  @override
  Widget build(BuildContext context) {
    Color bg;
    if (isPrimary) {
      bg = AppColors.primaryColor;
    } else if (isPending) {
      bg = AppColors.primaryColor.withValues(alpha: 0.15);
    } else if (isSecondary) {
      bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    } else {
      bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    }
    return Material(
      color: bg,
      borderRadius: BorderRadius.circular(24),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(24),
        child: Container(
          padding: EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w800,
              color: isPrimary ? Colors.white : (isPending ? AppColors.primaryColor : AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary)),
            ),
          ),
        ),
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  final String value;
  final String label;
  final bool hasDot;
  final VoidCallback onTap;
  final bool isDark;
  final Color fgPrimary;
  final Color fgSecondary;

  const _StatChip({
    required this.value,
    required this.label,
    required this.onTap,
    required this.isDark,
    required this.fgPrimary,
    required this.fgSecondary,
    this.hasDot = false,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: fgPrimary)),
                if (hasDot) ...[
                  SizedBox(width: 4),
                  Container(width: 10, height: 10, decoration: BoxDecoration(color: AppColors.error, shape: BoxShape.circle)),
                ],
              ],
            ),
            Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: fgSecondary)),
          ],
        ),
      ),
    );
  }
}

class _MoreMenuItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _MoreMenuItem({required this.icon, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: 56,
          height: 56,
          decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(16)),
          child: Icon(icon, color: color, size: 24),
        ),
        SizedBox(height: 8),
        Text(label, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w800)),
      ],
    );
  }
}
