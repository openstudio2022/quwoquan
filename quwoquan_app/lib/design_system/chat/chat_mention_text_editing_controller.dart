import 'package:flutter/material.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

enum ChatInputMentionKind { member, assistant, all }

/// 输入选择器返回的稳定提及目标。显示名只用于正文，发送语义只消费 [id]。
class ChatInputMentionCandidate {
  const ChatInputMentionCandidate({
    required this.id,
    required this.displayName,
    this.avatarUrl = '',
    this.kind = ChatInputMentionKind.member,
  });

  final String id;
  final String displayName;
  final String avatarUrl;
  final ChatInputMentionKind kind;
}

class _ChatMentionRange {
  const _ChatMentionRange({
    required this.id,
    required this.label,
    required this.start,
    required this.end,
  });

  final String id;
  final String label;
  final int start;
  final int end;

  _ChatMentionRange shift(int delta) => _ChatMentionRange(
    id: id,
    label: label,
    start: start + delta,
    end: end + delta,
  );
}

/// 维护正文中的提及 token 与稳定 ID 的对应关系。
///
/// 任意编辑只要触碰 token，就立即移除其发送语义；在 token 前后的普通编辑只平移
/// range。这样删除 `@显示名` 后不会残留隐形 mentions，也不需要从正文反向猜 ID。
class ChatMentionTextEditingController extends TextEditingController {
  ChatMentionTextEditingController({super.text}) {
    _lastValue = value;
    addListener(_reconcileMentionRanges);
  }

  late TextEditingValue _lastValue;
  List<_ChatMentionRange> _ranges = <_ChatMentionRange>[];
  bool _isApplyingMention = false;

  List<String> get activeMentionIds {
    final seen = <String>{};
    final ids = <String>[];
    final sorted = [..._ranges]..sort((a, b) => a.start.compareTo(b.start));
    for (final range in sorted) {
      if (seen.add(range.id)) {
        ids.add(range.id);
      }
    }
    return List<String>.unmodifiable(ids);
  }

  void replaceRangeWithMention({
    required int start,
    required int end,
    required ChatInputMentionCandidate mention,
  }) {
    final resolvedStart = start.clamp(0, text.length);
    final resolvedEnd = end.clamp(resolvedStart, text.length);
    final displayName = mention.displayName.trim();
    final id = mention.id.trim();
    if (displayName.isEmpty || id.isEmpty) {
      return;
    }
    final token = '@$displayName';
    final replacement = '$token ';
    final nextText =
        text.substring(0, resolvedStart) +
        replacement +
        text.substring(resolvedEnd);

    _isApplyingMention = true;
    value = TextEditingValue(
      text: nextText,
      selection: TextSelection.collapsed(
        offset: resolvedStart + replacement.length,
      ),
    );
    _isApplyingMention = false;
    _lastValue = value;
    final delta = replacement.length - (resolvedEnd - resolvedStart);
    final retained = <_ChatMentionRange>[];
    for (final range in _ranges) {
      if (range.end <= resolvedStart) {
        retained.add(range);
      } else if (range.start >= resolvedEnd) {
        retained.add(range.shift(delta));
      }
    }
    _ranges = [
      ...retained,
      _ChatMentionRange(
        id: id,
        label: token,
        start: resolvedStart,
        end: resolvedStart + token.length,
      ),
    ]..sort((a, b) => a.start.compareTo(b.start));
    notifyListeners();
  }

  void insertMentionAtSelection(ChatInputMentionCandidate mention) {
    final currentSelection = selection;
    final start = currentSelection.isValid
        ? currentSelection.start
        : text.length;
    final end = currentSelection.isValid ? currentSelection.end : text.length;
    replaceRangeWithMention(start: start, end: end, mention: mention);
  }

  void _reconcileMentionRanges() {
    final previous = _lastValue;
    final current = value;
    if (_isApplyingMention || previous.text == current.text) {
      _lastValue = current;
      return;
    }

    final oldText = previous.text;
    final newText = current.text;
    var prefix = 0;
    final sharedPrefixLimit = oldText.length < newText.length
        ? oldText.length
        : newText.length;
    while (prefix < sharedPrefixLimit &&
        oldText.codeUnitAt(prefix) == newText.codeUnitAt(prefix)) {
      prefix++;
    }

    var suffix = 0;
    final oldRemaining = oldText.length - prefix;
    final newRemaining = newText.length - prefix;
    final sharedSuffixLimit = oldRemaining < newRemaining
        ? oldRemaining
        : newRemaining;
    while (suffix < sharedSuffixLimit &&
        oldText.codeUnitAt(oldText.length - suffix - 1) ==
            newText.codeUnitAt(newText.length - suffix - 1)) {
      suffix++;
    }

    final oldChangeEnd = oldText.length - suffix;
    final delta = newText.length - oldText.length;
    final insertionOnly = prefix == oldChangeEnd;
    final nextRanges = <_ChatMentionRange>[];
    for (final range in _ranges) {
      final insertionTouchesToken =
          insertionOnly && prefix > range.start && prefix < range.end;
      final replacementTouchesToken =
          !insertionOnly && range.start < oldChangeEnd && range.end > prefix;
      if (insertionTouchesToken || replacementTouchesToken) {
        continue;
      }
      var next = range;
      if (range.start >= oldChangeEnd) {
        next = range.shift(delta);
      }
      if (next.start < 0 ||
          next.end > newText.length ||
          newText.substring(next.start, next.end) != next.label) {
        continue;
      }
      nextRanges.add(next);
    }
    _ranges = nextRanges;
    _lastValue = current;
  }

  @override
  TextSpan buildTextSpan({
    required BuildContext context,
    TextStyle? style,
    required bool withComposing,
  }) {
    final validRanges = [..._ranges]
      ..sort((a, b) => a.start.compareTo(b.start));
    final children = <InlineSpan>[];
    var cursor = 0;
    for (final range in validRanges) {
      if (range.start < cursor ||
          range.end > text.length ||
          text.substring(range.start, range.end) != range.label) {
        continue;
      }
      if (range.start > cursor) {
        children.add(TextSpan(text: text.substring(cursor, range.start)));
      }
      children.add(
        TextSpan(
          text: text.substring(range.start, range.end),
          style: style?.copyWith(
            color: AppColors.primaryColor,
            fontWeight: AppTypography.semiBold,
          ),
        ),
      );
      cursor = range.end;
    }
    if (cursor < text.length) {
      children.add(TextSpan(text: text.substring(cursor)));
    }
    return TextSpan(style: style, children: children);
  }

  @override
  void dispose() {
    removeListener(_reconcileMentionRanges);
    super.dispose();
  }
}
