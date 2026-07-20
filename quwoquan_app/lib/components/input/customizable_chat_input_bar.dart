import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/app/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/components/input/chat_mention_text_editing_controller.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

part 'customizable_chat_input_bar_attachments.part.dart';
part 'customizable_chat_input_bar_composer.part.dart';
part 'customizable_chat_input_bar_layout.part.dart';
part 'customizable_chat_input_bar_voice.part.dart';

/// 与 `CustomizableChatInputBar` 工具栏共享的图标规格（同文件内复用）。
const double _kChatInputToolbarGlyphSize = AppSpacing.iconMedium;
const double _kChatInputSendGlyphSize = AppSpacing.iconMedium + 1;
const IconData _kChatInputKeyboardCompactIcon = Icons.keyboard_outlined;
const IconData _kChatInputEmojiPanelIcon = Icons.sentiment_satisfied_alt;

enum ChatInputAttachmentType { image, file }

/// 输入区 `+` 面板中的自定义功能项（扩展点，宿主按需注入）
class ChatInputExtraPanelItem {
  const ChatInputExtraPanelItem({
    required this.icon,
    required this.text,
    required this.onTap,
    this.disabled = false,
  });

  final IconData icon;
  final String text;
  final Future<void> Function() onTap;
  final bool disabled;
}

class ChatInputAttachment {
  const ChatInputAttachment({
    required this.id,
    required this.type,
    required this.name,
    this.localPath,
    this.subtitle,
    this.thumbnailProvider,
  });

  final String id;
  final ChatInputAttachmentType type;
  final String name;
  final String? localPath;
  final String? subtitle;
  final ImageProvider? thumbnailProvider;
}

class ChatInputSubmitPayload {
  const ChatInputSubmitPayload({
    required this.text,
    required this.attachments,
    this.mentions = const <String>[],
  });

  final String text;
  final List<ChatInputAttachment> attachments;
  final List<String> mentions;
}

typedef ChatInputMentionRequester =
    Future<ChatInputMentionCandidate?> Function(BuildContext context);

enum ChatInputPanelMode { none, emoji, more }

class ChatInputVisualState {
  const ChatInputVisualState({
    required this.hasText,
    required this.hasAttachments,
    required this.isVoiceMode,
    required this.isRecording,
    required this.panelMode,
  });

  final bool hasText;
  final bool hasAttachments;
  final bool isVoiceMode;
  final bool isRecording;
  final ChatInputPanelMode panelMode;
}

class ChatInputDefaultActions {
  const ChatInputDefaultActions({
    required this.toggleAddPanel,
    required this.toggleVoiceMode,
    required this.toggleEmojiPanel,
    required this.send,
    required this.openExpandedEditor,
  });

  final VoidCallback toggleAddPanel;
  final VoidCallback toggleVoiceMode;
  final VoidCallback toggleEmojiPanel;
  final VoidCallback send;
  final VoidCallback openExpandedEditor;
}

typedef ChatInputLeftBuilder =
    Widget Function(
      BuildContext context,
      ChatInputVisualState state,
      ChatInputDefaultActions actions,
    );

typedef ChatInputRightBuilder =
    List<Widget> Function(
      BuildContext context,
      ChatInputVisualState state,
      ChatInputDefaultActions actions,
    );

class CustomizableChatInputBar extends StatefulWidget {
  const CustomizableChatInputBar({
    super.key,
    required this.onSend,
    this.controller,
    this.focusNode,
    this.textFieldKey,
    this.hintText,
    this.maxTextLength = 5000,
    this.maxVisibleLines = 5,
    this.maxAttachmentCount = 3,
    this.initialAttachments = const <ChatInputAttachment>[],
    this.onPickImages,
    this.onPickFiles,
    this.onCapturePhoto,
    this.onRequestMicPermission,
    this.onStartRecord,
    this.onStopRecord,
    this.onCancelRecord,
    this.voiceAmplitudeStream,
    this.onAttachmentChanged,
    this.onToast,
    this.onMentionRequested,
    this.showAddPanel = true,
    this.showEmojiButton = false,
    this.showXiaoquMentionButton = false,
    this.enableVoiceInput = false,
    this.enableExpandedEditor = true,
    this.disabled = false,
    this.sendButtonKey,
    this.leftBuilder,
    this.rightBuilder,
    this.extraPanelItems = const <ChatInputExtraPanelItem>[],
  });

  final TextEditingController? controller;
  final FocusNode? focusNode;
  final Key? textFieldKey;
  final String? hintText;
  final int maxTextLength;
  final int maxVisibleLines;
  final int maxAttachmentCount;
  final List<ChatInputAttachment> initialAttachments;
  final Future<List<ChatInputAttachment>> Function(int remaining)? onPickImages;
  final Future<List<ChatInputAttachment>> Function(int remaining)? onPickFiles;
  final Future<ChatInputAttachment?> Function()? onCapturePhoto;
  final Future<bool> Function()? onRequestMicPermission;
  final Future<bool> Function()? onStartRecord;
  final Future<void> Function(Duration duration)? onStopRecord;
  final Future<void> Function()? onCancelRecord;
  final Stream<List<double>>? voiceAmplitudeStream;
  final Future<void> Function(ChatInputSubmitPayload payload) onSend;
  final ValueChanged<List<ChatInputAttachment>>? onAttachmentChanged;
  final ValueChanged<String>? onToast;
  final ChatInputMentionRequester? onMentionRequested;
  final bool showAddPanel;
  final bool showEmojiButton;
  final bool showXiaoquMentionButton;
  final bool enableVoiceInput;
  final bool enableExpandedEditor;
  final bool disabled;
  final Key? sendButtonKey;
  final ChatInputLeftBuilder? leftBuilder;
  final ChatInputRightBuilder? rightBuilder;

  /// 注入到 `+` 面板中的自定义功能项（如语音通话、视频通话）
  final List<ChatInputExtraPanelItem> extraPanelItems;

  @override
  State<CustomizableChatInputBar> createState() =>
      _CustomizableChatInputBarState();
}

class _CustomizableChatInputBarState extends State<CustomizableChatInputBar>
    with SingleTickerProviderStateMixin {
  /// 与微信一致：输入/语音槽单行同高；多行时仅外轮廓四角为小圆角（非胶囊）。
  static const double _fieldCornerRadius = AppSpacing.smallBorderRadius;
  static const double _composerCenterMinHeight =
      AppSpacing.chatInputToolbarMinHeight;

  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  late final bool _isExternalController;
  late final bool _isExternalFocusNode;
  final ScrollController _textScrollController = ScrollController();
  final List<ChatInputAttachment> _attachments = <ChatInputAttachment>[];

  ChatInputPanelMode _panelMode = ChatInputPanelMode.none;
  bool _isVoiceMode = false;
  bool _isRecording = false;
  bool _isVoiceCancelling = false;
  bool _voicePointerActive = false;
  final Set<String> _pendingMentions = <String>{};
  late TextEditingValue _lastComposerValue;
  bool _mentionRequestInFlight = false;
  Offset? _voicePointerStartGlobal;
  DateTime? _recordStartAt;

  late final AnimationController _waveController;
  final List<double> _waveBars = List<double>.filled(24, 0.2, growable: true);
  Timer? _waveTicker;
  Timer? _voiceMaxTimer;
  Timer? _voiceElapsedTimer;
  StreamSubscription<List<double>>? _voiceAmplitudeSub;

  bool get _hasText => _controller.text.trim().isNotEmpty;
  bool get _hasAttachments => _attachments.isNotEmpty;
  bool get _canSend => !widget.disabled && (_hasText || _hasAttachments);
  bool get _showAddPanel => _panelMode == ChatInputPanelMode.more;
  bool get _showEmojiPanel => _panelMode == ChatInputPanelMode.emoji;

  void _updateState(VoidCallback update) => setState(update);

  Color _cupertinoColor(BuildContext context, CupertinoDynamicColor color) {
    return CupertinoDynamicColor.resolve(color, context);
  }

  Color _foregroundPrimary(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.label);

  Color _foregroundSecondary(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.secondaryLabel);

  Color _sheetBackground(BuildContext context) => _cupertinoColor(
    context,
    CupertinoColors.secondarySystemGroupedBackground,
  );

  Color _fieldBackground(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.systemBackground);

  Color _separatorColor(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.separator);

  /// 输入/语音槽填充：介于工具栏灰底与纯白之间，降低与条背景的对比度。
  Color _composerInputFill(BuildContext context) {
    final sheet = _sheetBackground(context);
    final field = _fieldBackground(context);
    return Color.lerp(sheet, field, 0.28) ?? field;
  }

  /// 与聊天气泡正文一致：Theme `bodyLarge` + 统一行高。
  TextStyle _composerTextStyle(BuildContext context) {
    final fontSize = AppTypography.base;
    return TextStyle(
      fontSize: fontSize,
      height: AppTypography.bodyLineHeight,
      color: _foregroundPrimary(context),
    );
  }

  @override
  void initState() {
    super.initState();
    _isExternalController = widget.controller != null;
    _isExternalFocusNode = widget.focusNode != null;
    _controller = widget.controller ?? TextEditingController();
    _focusNode = widget.focusNode ?? FocusNode();
    _attachments.addAll(widget.initialAttachments);
    _lastComposerValue = _controller.value;
    _controller.addListener(_onTextChanged);
    _focusNode.addListener(_onFocusChanged);
    _waveController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    );
  }

  @override
  void dispose() {
    _waveTicker?.cancel();
    _voiceMaxTimer?.cancel();
    _voiceElapsedTimer?.cancel();
    _voiceAmplitudeSub?.cancel();
    _waveController.dispose();
    _controller.removeListener(_onTextChanged);
    _focusNode.removeListener(_onFocusChanged);
    _textScrollController.dispose();
    if (!_isExternalController) {
      _controller.dispose();
    }
    if (!_isExternalFocusNode) {
      _focusNode.dispose();
    }
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant CustomizableChatInputBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.disabled || widget.disabled == oldWidget.disabled) {
      return;
    }
    if (_isRecording) {
      unawaited(_cancelVoiceRecord());
    }
    if (_focusNode.hasFocus) {
      _focusNode.unfocus();
    }
    setState(() {
      _isVoiceMode = false;
      _panelMode = ChatInputPanelMode.none;
    });
  }

  void _onTextChanged() {
    if (!mounted) return;
    final previous = _lastComposerValue;
    final current = _controller.value;
    _lastComposerValue = current;
    if (!_controller.text.contains(ChatText.commentAtXiaoqu)) {
      _pendingMentions.remove('assistant');
    }
    _requestMentionForNewAt(previous, current);
    setState(() {});
  }

  void _requestMentionForNewAt(
    TextEditingValue previous,
    TextEditingValue current,
  ) {
    final requester = widget.onMentionRequested;
    if (requester == null ||
        _mentionRequestInFlight ||
        !current.selection.isValid ||
        !current.selection.isCollapsed) {
      return;
    }
    final caret = current.selection.extentOffset;
    if (caret <= 0 ||
        caret > current.text.length ||
        current.text.substring(caret - 1, caret) != '@') {
      return;
    }
    final insertionOffset = (caret - 1).clamp(0, previous.text.length);
    final expected =
        '${previous.text.substring(0, insertionOffset)}@'
        '${previous.text.substring(insertionOffset)}';
    if (current.text != expected) {
      return;
    }
    _mentionRequestInFlight = true;
    unawaited(
      requester(context)
          .then((mention) {
            if (!mounted || mention == null) {
              return;
            }
            final triggerOffset = caret - 1;
            if (triggerOffset >= _controller.text.length ||
                _controller.text.substring(triggerOffset, triggerOffset + 1) !=
                    '@') {
              return;
            }
            final controller = _controller;
            if (controller is ChatMentionTextEditingController) {
              controller.replaceRangeWithMention(
                start: triggerOffset,
                end: triggerOffset + 1,
                mention: mention,
              );
            } else {
              final next =
                  '${controller.text.substring(0, triggerOffset)}'
                  '@${mention.displayName} '
                  '${controller.text.substring(triggerOffset + 1)}';
              controller.value = TextEditingValue(
                text: next,
                selection: TextSelection.collapsed(
                  offset: triggerOffset + mention.displayName.length + 2,
                ),
              );
              _pendingMentions.add(mention.id);
            }
          })
          .whenComplete(() {
            _mentionRequestInFlight = false;
          }),
    );
  }

  void _onFocusChanged() {
    if (!mounted || !_focusNode.hasFocus) {
      return;
    }
    if (_panelMode != ChatInputPanelMode.none) {
      setState(() => _panelMode = ChatInputPanelMode.none);
    }
  }

  void _emitToast(String text) {
    if (widget.onToast != null) {
      widget.onToast!(text);
      return;
    }
    AppToast.show(context, text);
  }

  @override
  Widget build(BuildContext context) => _buildInputBar();
}
