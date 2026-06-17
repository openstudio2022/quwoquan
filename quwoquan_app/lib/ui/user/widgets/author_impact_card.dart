import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/widgets/intersection_statement_card.dart';

/// 影响力摘要模块（他人主页 / 我的主页双视角，可解释）。
///
/// 只读直出 [AuthorImpactSummary] 的前 [maxItems] 条云侧 displayText 结论句
/// （如「23人加入相关圈子」），端不本地拼装文案（G2）；
/// other 模式无数据不占位，mine 模式空态展示鼓励发布文案。
class AuthorImpactCard extends StatelessWidget {
  const AuthorImpactCard({
    super.key,
    required this.summary,
    required this.isDark,
    required this.isMine,
    this.maxItems = 3,
  });

  static const Key cardKey = ValueKey<String>('author-impact-card');
  static const Key emptyKey = ValueKey<String>('author-impact-empty');

  final AuthorImpactSummary summary;
  final bool isDark;

  /// true = 我的主页；false = 他人主页。
  final bool isMine;
  final int maxItems;

  bool get _isEmpty =>
      summary.total <= 0 ||
      summary.items.every((item) => item.primaryText.trim().isEmpty);

  @override
  Widget build(BuildContext context) {
    if (_isEmpty && !isMine) {
      // 用户主页无影响事实不占位（不造假、不放占位数字）。
      return const SizedBox.shrink();
    }
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final visible = summary.items
        .where((item) => item.primaryText.trim().isNotEmpty)
        .take(maxItems)
        .toList(growable: false);

    return IntersectionStatementCard(
      key: AuthorImpactCard.cardKey,
      title: isMine
          ? UITextConstants.profileImpactTitleMine
          : UITextConstants.profileImpactTitleOther,
      items: _isEmpty
          ? const <IntersectionStatementItem>[]
          : <IntersectionStatementItem>[
              for (final item in visible)
                IntersectionStatementItem(
                  primaryText: item.primaryText.trim(),
                  subtitleText: _subtitleTextFor(
                    item.subtitleText,
                    item.source,
                  ),
                  highlight: _isStrongImpact(item.helpType)
                      ? IntersectionStatementHighlight.blue
                      : IntersectionStatementHighlight.gray,
                  onTap: () => _showEvidence(
                    context,
                    count: item.count,
                    displayText: item.primaryText.trim(),
                    source: item.source,
                    subtitleText: item.subtitleText,
                    isMine: isMine,
                  ),
                ),
            ],
      emptyChild: Text(
        key: AuthorImpactCard.emptyKey,
        UITextConstants.profileImpactEmptyMine,
        style: TextStyle(
          fontSize: AppTypography.iosCaption1,
          height: AppSpacing.textLineHeightBody,
          color: fgSecondary,
        ),
      ),
    );
  }

  static String _subtitleTextFor(String subtitleText, String source) {
    final subtitle = subtitleText.trim();
    if (subtitle.isNotEmpty) {
      return subtitle;
    }
    return source.trim();
  }

  static bool _isStrongImpact(String helpType) {
    switch (helpType) {
      case 'circle':
      case 'join_circle':
      case 'community':
      case 'entity':
      case 'relationship':
        return true;
      default:
        return false;
    }
  }

  static Future<void> _showEvidence(
    BuildContext context, {
    required int count,
    required String displayText,
    required String source,
    required String subtitleText,
    required bool isMine,
  }) {
    final sourceLabel = source.trim().isEmpty
        ? subtitleText.trim().isEmpty
              ? (isMine
                    ? UITextConstants.profileImpactTitleMine
                    : UITextConstants.profileImpactTitleOther)
              : subtitleText.trim()
        : source.trim();
    final hint = isMine
        ? UITextConstants.impactEnumerableHintMine
        : UITextConstants.impactEnumerableHintOther;
    final message = count > 0
        ? '$hint\n$sourceLabel · $count'
        : '$hint\n$sourceLabel';
    return showAppActionSheet<void>(
      context,
      title: displayText,
      message: message,
      sections: const <AppActionSheetSection<void>>[],
      cancelLabel: UITextConstants.confirm,
    );
  }
}
