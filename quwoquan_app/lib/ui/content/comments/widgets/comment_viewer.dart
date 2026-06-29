/// 评论查看入口 re-export。
///
/// 真正的卡片弹窗实现见 `comment_viewer_modal.dart`；统一输入态见
/// `comment_input_overlay.dart`。早期的 `CommentInput` / `CommentInputUtils`
/// 单行输入组件已随评论体验重设计移除。
library;

export 'comment_viewer_modal.dart' show CommentViewer;
