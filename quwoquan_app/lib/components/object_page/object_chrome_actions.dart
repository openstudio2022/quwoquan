import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 对象页顶栏右侧动作组（实体 / 圈子主页共享）。
///
/// 高保口径：封面右上「搜索 🔍 · AI ✨ · 分享 ↗ · 更多 ⚙︎」四图标，圆形热区随滚动
/// 渐变前景 / 底色，与左侧返回按钮同款 [ProfileIosIconButton]。
///
/// 行为以回调注入：搜索 / 分享 / 更多为 `VoidCallback`，AI 由本组件提供 [WidgetRef]
/// 供 ui 层调用全局助手 launcher——避免 components 层反向 import ui 层（分层 R01）。
class ObjectChromeActions extends ConsumerWidget {
  const ObjectChromeActions({
    super.key,
    required this.foregroundColor,
    required this.backgroundColor,
    required this.onSearch,
    required this.onAssistant,
    required this.onShare,
    this.onMore,
  });

  final Color foregroundColor;
  final Color backgroundColor;
  final VoidCallback onSearch;
  final void Function(WidgetRef ref) onAssistant;
  final VoidCallback onShare;

  /// 更多操作（对象操作面板：举报 / 纠错 / 维护 / 圈子管理）；null 时隐藏齿轮。
  final VoidCallback? onMore;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _action(
          keyValue: 'object-chrome-search',
          icon: CupertinoIcons.search,
          label: UITextConstants.search,
          onPressed: onSearch,
        ),
        SizedBox(width: AppSpacing.intraGroupXs),
        _action(
          keyValue: 'object-chrome-assistant',
          icon: CupertinoIcons.sparkles,
          label: AssistantText.assistantEntryXiaoqu,
          onPressed: () => onAssistant(ref),
        ),
        SizedBox(width: AppSpacing.intraGroupXs),
        _action(
          keyValue: 'object-chrome-share',
          icon: CupertinoIcons.arrowshape_turn_up_right,
          label: UITextConstants.share,
          onPressed: onShare,
        ),
        if (onMore != null) ...<Widget>[
          SizedBox(width: AppSpacing.intraGroupXs),
          _action(
            keyValue: 'object-chrome-more',
            icon: CupertinoIcons.gear,
            label: ChatText.more,
            onPressed: onMore!,
          ),
        ],
      ],
    );
  }

  Widget _action({
    required String keyValue,
    required IconData icon,
    required String label,
    required VoidCallback onPressed,
  }) {
    return Semantics(
      button: true,
      label: label,
      child: ProfileIosIconButton(
        key: ValueKey<String>(keyValue),
        icon: icon,
        onPressed: onPressed,
        backgroundColor: backgroundColor,
        foregroundColor: foregroundColor,
      ),
    );
  }
}
