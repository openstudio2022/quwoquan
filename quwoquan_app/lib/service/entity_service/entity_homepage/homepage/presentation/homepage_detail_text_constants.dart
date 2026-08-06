import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// 主页详情页专属文案门面。
///
/// 新增主页详情文案从 [UITextConstants] 大桶拆出，调用侧按页面职责依赖这里；
/// 已有共享基础文案仍留在 [UITextConstants]。
abstract final class HomepageDetailText {
  static const String reviewSummaryTitle = '口碑摘要';
  static const String basicInfoSectionTitle = '基础信息';
  static const String locationInfoTitle = '位置';
  static const String categoryInfoTitle = '分类';
  static const String establishedInfoTitle = '年份';
  static const String offlineNoticeTitle = '记录状态';
  static const String offlineNoticeMessage = '这里暂时不可关注，过往记录、讨论与关联内容会继续保留，方便回看。';

  static String relatedGroupMemberLine(String formattedCount) =>
      '$formattedCount ${ObjectHomepageText.homepageRelatedGroupSubtitle}';

  static const String relatedGroupOpenAction = '打开圈子';
  static const String relatedGroupDefaultReason = '围绕这里的记录与讨论正在沉淀';

  static String relatedGroupReasonFor(String objectName) =>
      '围绕$objectName的记录与讨论正在沉淀';
}
