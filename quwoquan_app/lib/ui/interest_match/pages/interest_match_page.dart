import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/interest_match_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

/// 找同趣 / 兴趣配对页（底栏 `+` 动作面板导流的发现入口）。
///
/// 定位为**发现启动器（launcher）**，而非内容流或独立候选列表：
/// - 不自建第二套 Mock 候选数据（守 08-mock-data-isolation / R16）；
/// - 按兴趣发现方式把用户导流到既有真实面：
///   - 找同趣的人 → 全局网络结果 `/search/network`；
///   - 找相关圈子 / 找想去的地方 / 按兴趣搜索 → 全局搜索 `/search`；
///   - 今日同趣机会 → 我的交集 `/profile/intersections`（真实交集承接）。
/// - 重行动（打招呼 / 同行 / 局）由目标真实面承接，不在此新增请求状态机。
///
/// 曝光埋点：进入页记录 `VisitTarget.page('interest_match')`（守 R20 曝光）。
class InterestMatchPage extends ConsumerStatefulWidget {
  const InterestMatchPage({super.key});

  static const Key viewKey = ValueKey<String>('interest-match-page');
  static const Key todayCtaKey = ValueKey<String>('interest-match-today-cta');
  static const Key findPeopleKey = ValueKey<String>(
    'interest-match-find-people',
  );
  static const Key findCirclesKey = ValueKey<String>(
    'interest-match-find-circles',
  );
  static const Key findPlacesKey = ValueKey<String>(
    'interest-match-find-places',
  );
  static const Key searchKey = ValueKey<String>('interest-match-search');
  static const Key backButtonKey = ValueKey<String>('interest-match-back');
  static const Key safetyNoteKey = ValueKey<String>(
    'interest-match-safety-note',
  );

  @override
  ConsumerState<InterestMatchPage> createState() => _InterestMatchPageState();
}

class _InterestMatchPageState extends ConsumerState<InterestMatchPage> {
  static const String _source = 'interest_match';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref
          .read(visitRecorderServiceProvider)
          .recordVisit(const VisitTarget.page(_source));
    });
  }

  void _openMyIntersections() {
    context.push(AppRoutePaths.myIntersections(sourceRef: _source));
  }

  void _openPeople() {
    context.push(AppRoutePaths.globalSearchNetworkResults());
  }

  void _openSearch() {
    context.push(AppRoutePaths.globalSearch);
  }

  void _handleBack() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(AppRoutePaths.home);
    }
  }

  @override
  Widget build(BuildContext context) {
    final background = AppColors.iosGroupedSurface(context);
    return AppScaffold(
      key: InterestMatchPage.viewKey,
      backgroundColor: background,
      navigationBar: AppNavigationBar(
        backgroundColor: background,
        border: null,
        automaticallyImplyLeading: false,
        leading: AppNavigationBarIconButton(
          key: InterestMatchPage.backButtonKey,
          icon: CupertinoIcons.back,
          onPressed: _handleBack,
        ),
      ),
      body: SafeArea(
        top: false,
        bottom: false,
        child: ListView(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.md,
            AppSpacing.md,
            AppSpacing.md,
            AppSpacing.lg,
          ),
          children: <Widget>[
            _buildHeader(context),
            SizedBox(height: AppSpacing.md),
            _buildLead(context),
            SizedBox(height: AppSpacing.md),
            _buildTodayCard(context),
            SizedBox(height: AppSpacing.lg),
            _buildSectionHeader(
              context,
              InterestMatchTextConstants.matchTitle,
              InterestMatchTextConstants.matchSubtitle,
            ),
            SizedBox(height: AppSpacing.sm),
            _buildDiscoveryGroup(context),
            SizedBox(height: AppSpacing.md),
            _buildSafetyNote(context),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          AppConceptConstants.interestMatchTitle,
          style: TextStyle(
            fontSize: AppTypography.iosTitle2,
            fontWeight: AppTypography.bold,
            color: AppColors.iosLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Text(
          AppConceptConstants.interestMatchSubtitle,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }

  Widget _buildLead(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurfaceElevated(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            InterestMatchTextConstants.lead,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              fontWeight: AppTypography.bold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            InterestMatchTextConstants.leadSubtitle,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.md),
          _PrimaryActionButton(
            key: InterestMatchPage.searchKey,
            icon: CupertinoIcons.search,
            label: InterestMatchTextConstants.searchCta,
            onTap: _openSearch,
          ),
        ],
      ),
    );
  }

  Widget _buildTodayCard(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return GestureDetector(
      key: InterestMatchPage.todayCtaKey,
      behavior: HitTestBehavior.opaque,
      onTap: _openMyIntersections,
      child: Container(
        padding: EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.iosGroupedSurfaceElevated(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
        ),
        child: Row(
          children: <Widget>[
            Container(
              width: AppSpacing.smallAvatarSize,
              height: AppSpacing.smallAvatarSize,
              decoration: BoxDecoration(
                color: accent.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
              ),
              child: Icon(
                CupertinoIcons.sparkles,
                size: AppSpacing.eighteen,
                color: accent,
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    InterestMatchTextConstants.todayTitle,
                    style: TextStyle(
                      fontSize: AppTypography.iosCallout,
                      fontWeight: AppTypography.bold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    InterestMatchTextConstants.todaySubtitle,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Row(
              children: <Widget>[
                Text(
                  InterestMatchTextConstants.todayCta,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.medium,
                    color: accent,
                  ),
                ),
                Icon(
                  CupertinoIcons.chevron_forward,
                  size: AppSpacing.fourteen,
                  color: accent,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionHeader(
    BuildContext context,
    String title,
    String subtitle,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          title,
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            fontWeight: AppTypography.bold,
            color: AppColors.iosLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Text(
          subtitle,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }

  Widget _buildDiscoveryGroup(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurfaceElevated(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
      ),
      child: Column(
        children: <Widget>[
          _DiscoveryRow(
            rowKey: InterestMatchPage.findPeopleKey,
            icon: CupertinoIcons.person_2_fill,
            title: InterestMatchTextConstants.findPeopleTitle,
            subtitle: InterestMatchTextConstants.findPeopleSubtitle,
            onTap: _openPeople,
          ),
          _rowDivider(context),
          _DiscoveryRow(
            rowKey: InterestMatchPage.findCirclesKey,
            icon: CupertinoIcons.circle_grid_hex_fill,
            title: InterestMatchTextConstants.findCirclesTitle,
            subtitle: InterestMatchTextConstants.findCirclesSubtitle,
            onTap: _openSearch,
          ),
          _rowDivider(context),
          _DiscoveryRow(
            rowKey: InterestMatchPage.findPlacesKey,
            icon: CupertinoIcons.location_fill,
            title: InterestMatchTextConstants.findPlacesTitle,
            subtitle: InterestMatchTextConstants.findPlacesSubtitle,
            onTap: _openSearch,
          ),
        ],
      ),
    );
  }

  Widget _rowDivider(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.md + AppSpacing.smallAvatarSize,
      ),
      child: Container(height: 0.5, color: AppColors.iosSeparator(context)),
    );
  }

  Widget _buildSafetyNote(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(
          CupertinoIcons.lock_shield,
          size: AppSpacing.fourteen,
          color: AppColors.iosSecondaryLabel(context),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: Text(
            key: InterestMatchPage.safetyNoteKey,
            InterestMatchTextConstants.safetyNote,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ),
      ],
    );
  }
}

class _PrimaryActionButton extends StatelessWidget {
  const _PrimaryActionButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
      color: AppColors.primaryColor,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Icon(icon, size: AppSpacing.eighteen, color: AppColors.white),
          SizedBox(width: AppSpacing.intraGroupSm),
          Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.medium,
              color: AppColors.white,
            ),
          ),
        ],
      ),
    );
  }
}

class _DiscoveryRow extends StatelessWidget {
  const _DiscoveryRow({
    required this.rowKey,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final Key rowKey;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return GestureDetector(
      key: rowKey,
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: <Widget>[
            Container(
              width: AppSpacing.smallAvatarSize,
              height: AppSpacing.smallAvatarSize,
              decoration: BoxDecoration(
                color: accent.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
              ),
              child: Icon(icon, size: AppSpacing.eighteen, color: accent),
            ),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: AppTypography.iosCallout,
                      fontWeight: AppTypography.medium,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.fourteen,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }
}
