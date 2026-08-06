/// 内容类型轴（ContentType）的端侧命名常量。
///
/// 唯一对齐 metadata 真相源 `_shared/types.yaml` 的 `ContentType` 枚举：
/// `image / video / micro / article`。
///
/// 作品（work）当前只有 image / video / article 三类；micro 是点滴（moment）
/// 轴的形态。注意：这里只承载"内容类型轴"。媒体方向（vertical/horizontal/square）、
/// 发布者类型（author/circle/official）、显示模式（single/grid）、
/// 以及 `audio`（属 MediaType/MessageType/CallType 轴）都不是内容类型，
/// 不得再混入本类。
class ContentTypeConstants {
  const ContentTypeConstants._();

  static const String image = 'image';
  static const String video = 'video';
  static const String micro = 'micro';
  static const String article = 'article';
}
