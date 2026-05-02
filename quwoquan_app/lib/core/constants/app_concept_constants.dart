/// 产品概念与命名规范
///
/// 遵循 app-global spec、InformationArchitecture v3.1、CONTENT_SPECIFICATION v3.0。
/// 严禁使用已弃用概念。
class AppConceptConstants {
  AppConceptConstants._();

  // ==================== 核心理念 ====================
  /// 核心理念：以兴趣为半径，画出我们的交集。
  static const String coreIdea = '以兴趣为半径，画出我们的交集。';

  // ==================== 私人助理（Personal Assistant） ====================
  /// 助理会话/发送者固定 ID，逻辑判断用，不做展示
  static const String assistantConversationId = 'assistant';

  /// 助理发送者 ID，消息气泡/头像判断用
  static const String assistantSenderId = 'assistant';

  /// 助理 Slogan（可配置展示名）
  static const String assistantSlogan = '让兴趣闪亮';

  /// 助理拟人化名称（可配置）
  static const String assistantName = '智多星';

  /// 助理入口标签（用于底部主导航）
  static const String assistantTabLabel = '私助';

  /// 助理展示名（用于对话、设置等文案）
  static const String assistantLabel = '私助';

  /// 助理页标题
  static const String assistantDisplayTitle = '私助';

  /// 助理管理页标题：如「小趣管理」
  static String get assistantManagementTitle => '$assistantLabel管理';

  /// 清除记忆确认说明（含助理展示名）
  static String get assistantClearMemoryWarning =>
      '此操作将彻底删除$assistantLabel记录的关于你的所有行为数据、偏好模型及记录总结，操作不可撤销。';

  /// 助理参考外链默认黑名单；可通过 contextScopeHint.privacyPolicy.blockedReferenceHosts 覆盖。
  static const List<String> assistantReferenceHostBlocklist = <String>[];

  // ==================== 内容与创作概念 ====================
  /// 微趣：快速记录当下（照片九宫格、纯文字、短视频）
  static const String weiqu = '微趣';

  /// 微趣副标题
  static const String weiquSubtitle = '记录生活此刻感悟';

  /// 作品：精心打磨的图片/视频/文章内容
  static const String zuopin = '作品';

  /// 作品副标题
  static const String zuopinSubtitle = '精心创作优质内容';

  /// 创作 Tab
  static const String creation = '创作';

  /// 互动 Tab
  static const String interaction = '互动';

  /// 生活 Tab
  static const String life = '生活';

  // ==================== 生活子分类 ====================
  static const String footprint = '足迹';
  static const String bookMovieMusic = '书影音';
  static const String taste = '味蕾';
  static const String aiwu = '爱物';

  // ==================== 创作子分类 ====================
  static const String all = '全部';
  static const String images = '图片';
  static const String videos = '视频';
  static const String articles = '文章';

  // ==================== 五大频道 ====================
  static const String discovery = '首页';
  static const String circles = '群组';
  static const String create = '创作';
  static const String chat = '趣信';
  static const String profile = '我的';

  // ==================== 趣聊 Tab ====================
  static const String messages = '消息';
  static const String contacts = '联系人';

  // ==================== 创作入口 - 微趣三类 ====================
  static const String weiquPhoto = '照片';
  static const String weiquPhotoHint = '相册选择';
  static const String weiquText = '文字';
  static const String weiquTextHint = '纯文字';
  static const String weiquVideo = '视频';
  static const String weiquVideoHint = '短视频';

  // ==================== 创作入口 - 作品三类 ====================
  static const String zuopinImage = '图片';
  static const String zuopinImageHint = '大图展示';
  static const String zuopinArticle = '文章';
  static const String zuopinArticleHint = '长文图文';
  static const String zuopinVideo = '视频';
  static const String zuopinVideoHint = '精美视频';

  // ==================== 已弃用概念（严禁使用） ====================
  // 瞬间 (Moments) -> 已由微趣或创作取代
  // 随记 (Notes) -> 已合并至文章或生活记录
  // 好物 (Goods) -> 已整合进爱物
}
