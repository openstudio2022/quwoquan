/// Z-Index 层级常量
///
/// 基于 routing-and-user-journeys.md 定义的叠加层层级规范。
/// 数值越大越靠前。
class ZIndexConstants {
  ZIndexConstants._();

  /// 主框架（底部导航 + 当前频道）
  static const int mainFrame = 0;

  /// 底部导航栏
  static const int bottomNav = 50;

  /// 作者主页、圈子主页
  static const int authorProfile = 100;
  static const int circleProfile = 100;

  /// 创作页（CreatePage）
  static const int createPage = 120;

  /// 文章详情
  static const int articleDetail = 130;

  /// 沉浸式媒体查看器
  static const int mediaViewer = 150;

  /// 评论页
  static const int comments = 160;

  /// 创作入口抽屉 (CreateEntrySheet)
  static const int createEntrySheet = 170;

  /// PostActionSheet
  static const int actionSheet = 180;

  /// 欢迎页
  static const int welcome = 1000;

  /// 私人助理首页（在 MessagePage 内）
  static const int assistantHome = 3000;

  /// 私人助理管理页
  static const int assistantManagement = 3100;
}
