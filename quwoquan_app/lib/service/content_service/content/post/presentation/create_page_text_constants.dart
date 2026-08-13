/// 创作页专属文案门面。
///
/// 页面局部新增文案从 [UITextConstants] 大桶拆出，避免共享常量文件继续膨胀。
abstract final class CreatePageText {
  static const String photoPageTitle = '图片创作';

  /// 共同经历回流上下文条（发布回顾）。
  static const String gatheringContextPrefix = '来自：';
  static const String gatheringContextSuffix = ' · 发布到这次共同经历';
  static const String gatheringContextFallbackTitle = '这次行动';
  static const String gatheringContextRemove = '移除关联';
  static const String titleFieldLabel = '标题';
  static const String writeSomethingFirst = '先写点内容';
  static const String publishNotCompleted = '发布未完成';
  static const String activePersonaContextNotReady = '当前分身上下文还没准备好，稍后可以再试一次。';
  static const String uploadCancelledDraftSaved = '已取消上传，草稿已保存';
  static const String uploadCancelling = '正在取消';
  static const String cancelUpload = '取消';
  static const String publicationSubmitting = '正在提交发布，请稍候';
  static const String nextStep = '下一步';
  static const String paper = '纸张';
  static const String font = '字体';
  static const String editorFallbackBanner = '当前处于编辑器回退模式，保留双编辑器骨架并关闭增强提示。';
  static const String articleTitlePlaceholder = '输入文章标题（可选）';
  static const String articleBodyPlaceholder = '继续写内容，支持 emoji、图片、序号和模板';
  static const String articleBodyStartPlaceholder = '+ 想写点什么';
  static const String imageCaptionPlaceholder = '添加图片说明';
  static const String imageLayoutFullWidth = '全宽';
  static const String imageLayoutLeft = '左图';
  static const String imageLayoutRight = '右图';
  static const String edit = '编辑';
  static const String delete = '删除';
  static const String image = '图片';
  static const String mentionObject = '提及对象';
  static const String undo = '撤销';
  static const String redo = '重做';
  static const String recentEmoji = '最近使用';
  static const String allEmoji = '全部表情';
  static const String emojiPanelKeyboardHint = '表情面板与系统键盘共用同一高度，切换时不改变工具栏位置。';
  static const String headingLarge = '大标题';
  static const String headingSmall = '小标题';
  static const String quote = '引用';
  static const String bold = '加粗';
  static const String italic = '斜体';
  static const String underline = '下划线';
  static const String listSection = '序号';
  static const String numberedList = '1. 数字序号';
  static const String bulletedList = '• 圆点序号';
  static const String cover = '封面';
  static const String template = '模版';
  static const String coverEmptyHint = '插入图片后可把其中一张设为扉页封面';
  static const String noCover = '无封面';
  static const String typographyQualityTitle = '高质量文字排版';
  static const String fontPreviewGlyph = '文';
  static const String fontPreviewSample = '春江';
  static const String articleReaderPreviewSample = '春风起，纸面轻轻落下';
  static const String markdownHtmlNotAllowed = 'QWQ Rich Markdown 不允许任意 HTML';
  static const String markdownFrontMatterUnclosed = 'front matter 缺少结束 ---';
  static const String markdownFrontMatterInvalid = 'front matter 解析失败';
  static const String markdownDirectiveInvalid = '富布局指令格式不合法';

  static String maxImagesToast(int maxImages) => '最多添加 $maxImages 张图片';
  static String coverLabel(int index) => '封面 $index';
  static String markdownDirectiveUnclosed(String name) => '$name 指令缺少结束 :::';
  static String markdownDirectiveNotAllowed(String name) => '未知富布局指令 $name';
}
