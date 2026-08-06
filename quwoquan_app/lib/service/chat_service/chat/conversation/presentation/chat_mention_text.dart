import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

class ChatMentionTextSegment {
  const ChatMentionTextSegment({required this.text, this.targetId});

  final String text;
  final String? targetId;

  bool get isMention => targetId != null;
}

class _MentionTokenMatch {
  const _MentionTokenMatch({
    required this.start,
    required this.end,
    required this.text,
  });

  final int start;
  final int end;
  final String text;
}

/// 只把 `mentions` 中的稳定目标映射到正文 token；普通孤立 `@` 不会高亮。
List<ChatMentionTextSegment> resolveChatMentionTextSegments({
  required String content,
  required List<String> mentions,
  required Map<String, String> displayNames,
}) {
  if (content.isEmpty || mentions.isEmpty) {
    return <ChatMentionTextSegment>[ChatMentionTextSegment(text: content)];
  }
  final canonicalMentions = <String>[];
  final seen = <String>{};
  for (final raw in mentions) {
    final id = raw.trim();
    if (id.isNotEmpty && seen.add(id)) {
      canonicalMentions.add(id);
    }
  }
  final assignments = <int, String>{};
  final expectedLabels = <String, String>{};
  for (final id in canonicalMentions) {
    final displayName = switch (id) {
      '__all__' => '所有人',
      'assistant' => '小趣',
      _ => displayNames[id]?.trim() ?? '',
    };
    if (displayName.isNotEmpty) {
      expectedLabels[id] = '@$displayName';
    }
  }

  // 优先按当前 roster 的完整显示名定位，显示名可合法包含空格。名称不可用或历史
  // 正文已改名时，再回退到普通 @token 顺序；metadata mentions 始终是目标真相源。
  final tokens = <_MentionTokenMatch>[];
  final labelsByLength = expectedLabels.values.toSet().toList(growable: false)
    ..sort((a, b) => b.length.compareTo(a.length));
  for (final label in labelsByLength) {
    var offset = 0;
    while (offset < content.length) {
      final start = content.indexOf(label, offset);
      if (start < 0) {
        break;
      }
      final end = start + label.length;
      final candidate = _MentionTokenMatch(start: start, end: end, text: label);
      if (_hasMentionBoundaryAfter(content, end) &&
          !tokens.any((token) => _overlaps(token, candidate))) {
        tokens.add(candidate);
      }
      offset = start + 1;
    }
  }
  for (final match in RegExp(r'@[^\s@，。！？、,.!?;；:：]+').allMatches(content)) {
    final candidate = _MentionTokenMatch(
      start: match.start,
      end: match.end,
      text: match.group(0) ?? '',
    );
    if (candidate.text.length > 1 &&
        !tokens.any((token) => _overlaps(token, candidate))) {
      tokens.add(candidate);
    }
  }
  tokens.sort((a, b) => a.start.compareTo(b.start));
  if (tokens.isEmpty) {
    return <ChatMentionTextSegment>[ChatMentionTextSegment(text: content)];
  }

  for (final id in canonicalMentions) {
    final expected = expectedLabels[id];
    int? selected;
    if (expected != null) {
      for (var index = 0; index < tokens.length; index++) {
        if (!assignments.containsKey(index) && tokens[index].text == expected) {
          selected = index;
          break;
        }
      }
    }
    if (selected == null) {
      for (var index = 0; index < tokens.length; index++) {
        if (!assignments.containsKey(index)) {
          selected = index;
          break;
        }
      }
    }
    if (selected != null) {
      assignments[selected] = id;
    }
  }

  final uniquelyAssignedLabels = <String, String>{};
  final ambiguousLabels = <String>{};
  for (final entry in assignments.entries) {
    final label = tokens[entry.key].text;
    final previous = uniquelyAssignedLabels[label];
    if (previous == null) {
      uniquelyAssignedLabels[label] = entry.value;
    } else if (previous != entry.value) {
      ambiguousLabels.add(label);
    }
  }
  for (var index = 0; index < tokens.length; index++) {
    if (assignments.containsKey(index)) {
      continue;
    }
    final label = tokens[index].text;
    if (!ambiguousLabels.contains(label)) {
      final target = uniquelyAssignedLabels[label];
      if (target != null) {
        assignments[index] = target;
      }
    }
  }

  final segments = <ChatMentionTextSegment>[];
  var cursor = 0;
  for (var index = 0; index < tokens.length; index++) {
    final token = tokens[index];
    if (token.start > cursor) {
      segments.add(
        ChatMentionTextSegment(text: content.substring(cursor, token.start)),
      );
    }
    segments.add(
      ChatMentionTextSegment(
        text: content.substring(token.start, token.end),
        targetId: assignments[index],
      ),
    );
    cursor = token.end;
  }
  if (cursor < content.length) {
    segments.add(ChatMentionTextSegment(text: content.substring(cursor)));
  }
  return segments;
}

bool _hasMentionBoundaryAfter(String content, int end) {
  if (end >= content.length) {
    return true;
  }
  return RegExp(r'[\s，。！？、,.!?;；:：]').hasMatch(content[end]);
}

bool _overlaps(_MentionTokenMatch left, _MentionTokenMatch right) {
  return left.start < right.end && right.start < left.end;
}

/// Inline mention renderer owned by the conversation presentation.
class ChatMentionText extends StatefulWidget {
  const ChatMentionText({
    super.key,
    required this.content,
    required this.mentions,
    required this.displayNames,
    required this.style,
    required this.mentionStyle,
    this.textAlign = TextAlign.start,
    this.onMentionTap,
  });

  final String content;
  final List<String> mentions;
  final Map<String, String> displayNames;
  final TextStyle style;
  final TextStyle mentionStyle;
  final TextAlign textAlign;
  final ValueChanged<String>? onMentionTap;

  @override
  State<ChatMentionText> createState() => _ChatMentionTextState();
}

class _ChatMentionTextState extends State<ChatMentionText> {
  final List<TapGestureRecognizer> _recognizers = <TapGestureRecognizer>[];

  @override
  void dispose() {
    for (final recognizer in _recognizers) {
      recognizer.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    for (final recognizer in _recognizers) {
      recognizer.dispose();
    }
    _recognizers.clear();
    final segments = resolveChatMentionTextSegments(
      content: widget.content,
      mentions: widget.mentions,
      displayNames: widget.displayNames,
    );
    final spans = <InlineSpan>[];
    for (final segment in segments) {
      final targetID = segment.targetId;
      if (targetID == null) {
        spans.add(TextSpan(text: segment.text));
        continue;
      }
      TapGestureRecognizer? recognizer;
      if (widget.onMentionTap != null) {
        recognizer = TapGestureRecognizer()
          ..onTap = () => widget.onMentionTap!(targetID);
        _recognizers.add(recognizer);
      }
      spans.add(
        TextSpan(
          text: segment.text,
          style: widget.mentionStyle,
          recognizer: recognizer,
        ),
      );
    }
    return SelectableText.rich(
      TextSpan(children: spans),
      style: widget.style,
      textAlign: widget.textAlign,
    );
  }
}
