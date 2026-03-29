import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

/// 与 `CustomizableChatInputBar` 工具栏共享的图标规格（同文件内复用）。
const double _kChatInputToolbarGlyphSize = AppSpacing.iconMedium + 2;
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
    this.subtitle,
    this.thumbnailProvider,
  });

  final String id;
  final ChatInputAttachmentType type;
  final String name;
  final String? subtitle;
  final ImageProvider? thumbnailProvider;
}

class ChatInputSubmitPayload {
  const ChatInputSubmitPayload({
    required this.text,
    required this.attachments,
    required this.isVoiceMessage,
    this.voiceDuration = Duration.zero,
  });

  final String text;
  final List<ChatInputAttachment> attachments;
  final bool isVoiceMessage;
  final Duration voiceDuration;
}

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
    this.onVoiceAsrTransform,
    this.onAttachmentChanged,
    this.onToast,
    this.showAddPanel = true,
    this.showEmojiButton = false,
    this.enableExpandedEditor = true,
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
  final Future<void> Function()? onStartRecord;
  final Future<void> Function(Duration duration)? onStopRecord;
  final Future<String?> Function(Duration duration)? onVoiceAsrTransform;
  final Future<void> Function(ChatInputSubmitPayload payload) onSend;
  final ValueChanged<List<ChatInputAttachment>>? onAttachmentChanged;
  final ValueChanged<String>? onToast;
  final bool showAddPanel;
  final bool showEmojiButton;
  final bool enableExpandedEditor;
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
  static const double _composerCenterMinHeight = AppSpacing.buttonHeight;

  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  late final bool _isExternalController;
  late final bool _isExternalFocusNode;
  final ScrollController _textScrollController = ScrollController();
  final List<ChatInputAttachment> _attachments = <ChatInputAttachment>[];

  ChatInputPanelMode _panelMode = ChatInputPanelMode.none;
  bool _isVoiceMode = false;
  bool _isRecording = false;
  DateTime? _recordStartAt;

  late final AnimationController _waveController;
  final List<double> _waveBars = List<double>.filled(24, 0.2);
  Timer? _waveTicker;

  bool get _hasText => _controller.text.trim().isNotEmpty;
  bool get _hasAttachments => _attachments.isNotEmpty;
  bool get _canSend => _hasText || _hasAttachments;
  bool get _showAddPanel => _panelMode == ChatInputPanelMode.more;
  bool get _showEmojiPanel => _panelMode == ChatInputPanelMode.emoji;

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
    final fontSize =
        Theme.of(context).textTheme.bodyLarge?.fontSize ?? AppSpacing.md;
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

  void _onTextChanged() {
    if (!mounted) return;
    setState(() {});
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

  bool _acceptAttachmentType(ChatInputAttachmentType type) {
    if (_attachments.isEmpty) return true;
    final existingType = _attachments.first.type;
    if (existingType == type) return true;
    _emitToast(UITextConstants.chatAttachmentTypeConflict);
    return false;
  }

  int get _remainingAttachmentCount =>
      math.max(0, widget.maxAttachmentCount - _attachments.length);

  Future<void> _addAttachments(List<ChatInputAttachment> attachments) async {
    if (attachments.isEmpty) return;
    if (_attachments.length >= widget.maxAttachmentCount) {
      _emitToast(
        UITextConstants.chatAttachmentMaxCount.replaceFirst(
          '%s',
          widget.maxAttachmentCount.toString(),
        ),
      );
      return;
    }
    final type = attachments.first.type;
    if (!_acceptAttachmentType(type)) return;
    final canAdd = _remainingAttachmentCount;
    final toAdd = attachments.take(canAdd).toList(growable: false);
    if (toAdd.isEmpty) return;
    setState(() {
      _attachments.addAll(toAdd);
    });
    widget.onAttachmentChanged?.call(
      List<ChatInputAttachment>.from(_attachments),
    );
    if (attachments.length > canAdd) {
      _emitToast(
        UITextConstants.chatAttachmentMaxCount.replaceFirst(
          '%s',
          widget.maxAttachmentCount.toString(),
        ),
      );
    }
  }

  Future<void> _pickImages() async {
    if (widget.onPickImages == null) return;
    if (!_acceptAttachmentType(ChatInputAttachmentType.image)) return;
    final list = await widget.onPickImages!(_remainingAttachmentCount);
    if (!mounted) return;
    await _addAttachments(list);
  }

  Future<void> _pickFiles() async {
    if (widget.onPickFiles == null) return;
    if (!_acceptAttachmentType(ChatInputAttachmentType.file)) return;
    final list = await widget.onPickFiles!(_remainingAttachmentCount);
    if (!mounted) return;
    await _addAttachments(list);
  }

  Future<void> _capturePhoto() async {
    if (widget.onCapturePhoto == null) return;
    if (!_acceptAttachmentType(ChatInputAttachmentType.image)) return;
    final item = await widget.onCapturePhoto!();
    if (!mounted || item == null) return;
    await _addAttachments(<ChatInputAttachment>[item]);
  }

  void _removeAttachment(String id) {
    setState(() {
      _attachments.removeWhere((item) => item.id == id);
    });
    widget.onAttachmentChanged?.call(
      List<ChatInputAttachment>.from(_attachments),
    );
  }

  void _toggleAddPanel() {
    if (!widget.showAddPanel) return;
    setState(() {
      _panelMode = _showAddPanel
          ? ChatInputPanelMode.none
          : ChatInputPanelMode.more;
      if (_panelMode == ChatInputPanelMode.more) {
        _focusNode.unfocus();
      }
    });
  }

  void _toggleEmojiPanel() {
    if (!widget.showEmojiButton) return;
    setState(() {
      _panelMode = _showEmojiPanel
          ? ChatInputPanelMode.none
          : ChatInputPanelMode.emoji;
      if (_panelMode == ChatInputPanelMode.emoji) {
        _focusNode.unfocus();
      } else if (!_isVoiceMode) {
        _focusNode.requestFocus();
      }
    });
  }

  void _toggleVoiceMode() {
    setState(() {
      _isVoiceMode = !_isVoiceMode;
      _panelMode = ChatInputPanelMode.none;
      if (_isVoiceMode) {
        _focusNode.unfocus();
      } else {
        _focusNode.requestFocus();
      }
    });
  }

  Future<void> _send() async {
    if (!_canSend) return;
    final payload = ChatInputSubmitPayload(
      text: _controller.text.trim(),
      attachments: List<ChatInputAttachment>.from(_attachments),
      isVoiceMessage: false,
      voiceDuration: Duration.zero,
    );
    final hadAttachments = _attachments.isNotEmpty;
    setState(() {
      _controller.clear();
      _attachments.clear();
      _panelMode = ChatInputPanelMode.none;
    });
    if (hadAttachments) {
      widget.onAttachmentChanged?.call(const <ChatInputAttachment>[]);
    }
    await widget.onSend(payload);
  }

  Future<void> _startVoiceRecord() async {
    if (_isRecording) return;
    final hasPermission =
        await (widget.onRequestMicPermission?.call() ??
            Future<bool>.value(true));
    if (!mounted) return;
    if (!hasPermission) {
      _emitToast(UITextConstants.chatVoicePermissionDenied);
      return;
    }
    _recordStartAt = DateTime.now();
    setState(() => _isRecording = true);
    await widget.onStartRecord?.call();
    _startWave();
  }

  Future<void> _stopVoiceRecordAndSend() async {
    if (!_isRecording) return;
    final start = _recordStartAt ?? DateTime.now();
    final duration = DateTime.now().difference(start);
    _recordStartAt = null;
    _stopWave();
    setState(() => _isRecording = false);
    await widget.onStopRecord?.call(duration);
    final asrText = await widget.onVoiceAsrTransform?.call(duration);
    if (!mounted) return;
    final payload = ChatInputSubmitPayload(
      text: (asrText ?? '').trim(),
      attachments: const <ChatInputAttachment>[],
      isVoiceMessage: true,
      voiceDuration: duration,
    );
    await widget.onSend(payload);
  }

  void _startWave() {
    if (!_waveController.isAnimating) {
      _waveController.repeat(reverse: true);
    }
    _waveTicker?.cancel();
    _waveTicker = Timer.periodic(const Duration(milliseconds: 56), (_) {
      if (!mounted || !_isRecording) return;
      setState(() {
        for (var i = 0; i < _waveBars.length; i++) {
          final seed =
              (DateTime.now().millisecondsSinceEpoch / 1000) + i * 0.23;
          final base = (math.sin(seed * 4.2) + 1) / 2;
          _waveBars[i] = 0.15 + base * 0.85;
        }
      });
    });
  }

  void _stopWave() {
    _waveTicker?.cancel();
    _waveTicker = null;
    _waveController.stop();
    _waveController.reset();
    setState(() {
      for (var i = 0; i < _waveBars.length; i++) {
        _waveBars[i] = 0.2;
      }
    });
  }

  ChatInputVisualState _visualState() {
    return ChatInputVisualState(
      hasText: _hasText,
      hasAttachments: _hasAttachments,
      isVoiceMode: _isVoiceMode,
      isRecording: _isRecording,
      panelMode: _panelMode,
    );
  }

  ChatInputDefaultActions _defaultActions() {
    return ChatInputDefaultActions(
      toggleAddPanel: _toggleAddPanel,
      toggleVoiceMode: _toggleVoiceMode,
      toggleEmojiPanel: _toggleEmojiPanel,
      send: () {
        unawaited(_send());
      },
      openExpandedEditor: () {
        unawaited(_openExpandedEditor());
      },
    );
  }

  Future<void> _openExpandedEditor() async {
    if (!widget.enableExpandedEditor || _isVoiceMode) {
      return;
    }
    final shouldRefocus = _focusNode.hasFocus;
    final draft = await Navigator.of(context).push<_ExpandedInputDraft>(
      CupertinoPageRoute<_ExpandedInputDraft>(
        fullscreenDialog: true,
        builder: (context) => _ExpandedChatInputPage(
          initialText: _controller.text,
          hintText: widget.hintText ?? UITextConstants.inputHint,
          showEmojiButton: widget.showEmojiButton,
        ),
      ),
    );
    if (!mounted || draft == null) {
      return;
    }
    _controller.value = TextEditingValue(
      text: draft.text,
      selection: TextSelection.collapsed(offset: draft.text.length),
    );
    setState(() {
      _panelMode = draft.openEmojiPanel && widget.showEmojiButton
          ? ChatInputPanelMode.emoji
          : ChatInputPanelMode.none;
    });
    if (shouldRefocus && !_showEmojiPanel) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          _focusNode.requestFocus();
        }
      });
    }
  }

  List<Widget> _buildTrailingButtons(BuildContext context) {
    final buttons = <Widget>[];
    if (widget.showEmojiButton) {
      buttons.add(
        _buildToolbarPlainIconButton(
          context: context,
          key: TestKeys.chatInputEmojiToggleButton,
          icon: _showEmojiPanel
              ? _kChatInputKeyboardCompactIcon
              : _kChatInputEmojiPanelIcon,
          onTap: _toggleEmojiPanel,
          semanticLabel: _showEmojiPanel
              ? UITextConstants.keyboard
              : UITextConstants.emoji,
        ),
      );
    }
    if (widget.showEmojiButton && (_canSend || widget.showAddPanel)) {
      buttons.add(SizedBox(width: AppSpacing.xs));
    }
    if (_canSend) {
      buttons.add(_buildSendButton(context));
      return buttons;
    }
    if (widget.showAddPanel) {
      buttons.add(
        _buildToolbarPlainIconButton(
          context: context,
          key: TestKeys.chatInputMoreButton,
          icon: CupertinoIcons.add,
          onTap: _toggleAddPanel,
          semanticLabel: UITextConstants.more,
        ),
      );
    }
    return buttons;
  }

  /// 与工具栏底同色语义：无圆框、透明热区，图标即按钮。
  Widget _buildToolbarPlainIconButton({
    required BuildContext context,
    Key? key,
    required IconData icon,
    required VoidCallback onTap,
    required String semanticLabel,
    double iconSize = _kChatInputToolbarGlyphSize,
  }) {
    final diameter = AppSpacing.iconButtonMinSizeSm;
    final fg = _foregroundPrimary(context).withValues(alpha: 0.82);
    return Semantics(
      button: true,
      label: semanticLabel,
      child: CupertinoButton(
        key: key,
        padding: EdgeInsets.zero,
        minimumSize: Size(diameter, diameter),
        onPressed: onTap,
        child: Icon(icon, size: iconSize, color: fg),
      ),
    );
  }

  Widget _buildSendButton(BuildContext context) {
    return Semantics(
      button: true,
      label: UITextConstants.send,
      onTap: _send,
      child: GestureDetector(
        key: widget.sendButtonKey,
        onTap: _send,
        child: Container(
          width: AppSpacing.buttonSize,
          height: AppSpacing.buttonSize,
          decoration: BoxDecoration(
            color: AppColors.primaryColor,
            borderRadius: BorderRadius.circular(AppSpacing.buttonSize),
          ),
          alignment: Alignment.center,
          child: Icon(
            Icons.arrow_upward_rounded,
            size: _kChatInputSendGlyphSize,
            color: _fieldBackground(context),
          ),
        ),
      ),
    );
  }

  Widget _buildAttachmentPreview() {
    if (_attachments.isEmpty) return const SizedBox.shrink();
    final secondaryText = _foregroundSecondary(context);
    return SizedBox(
      height: AppSpacing.buttonSize + AppSpacing.sm,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        child: Row(
          children: _attachments
              .map((item) {
                final bg = item.type == ChatInputAttachmentType.image
                    ? _sheetBackground(context)
                    : _sheetBackground(context).withValues(alpha: 0.82);
                return Container(
                  width: AppSpacing.twoHundredTwenty,
                  margin: EdgeInsets.only(right: AppSpacing.sm),
                  padding: EdgeInsets.all(AppSpacing.sm),
                  decoration: BoxDecoration(
                    color: bg,
                    borderRadius: BorderRadius.circular(
                      AppSpacing.borderRadius,
                    ),
                  ),
                  child: Row(
                    children: [
                      _buildAttachmentLeading(item),
                      SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              item.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: AppTypography.base,
                                color: _foregroundPrimary(
                                  context,
                                ).withValues(alpha: 0.88),
                              ),
                            ),
                            if ((item.subtitle ?? '').trim().isNotEmpty)
                              Text(
                                item.subtitle!,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.sm,
                                  color: secondaryText,
                                ),
                              ),
                          ],
                        ),
                      ),
                      SizedBox(width: AppSpacing.xs),
                      GestureDetector(
                        onTap: () => _removeAttachment(item.id),
                        child: Container(
                          width: AppSpacing.iconButtonMinSizeSm,
                          height: AppSpacing.iconButtonMinSizeSm,
                          alignment: Alignment.center,
                          child: Icon(
                            Icons.close,
                            size: AppSpacing.iconSmall,
                            color: secondaryText,
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              })
              .toList(growable: false),
        ),
      ),
    );
  }

  Widget _buildAttachmentLeading(ChatInputAttachment item) {
    final radius = BorderRadius.circular(AppSpacing.smallBorderRadius);
    if (item.thumbnailProvider != null) {
      return ClipRRect(
        borderRadius: radius,
        child: Image(
          image: item.thumbnailProvider!,
          width: AppSpacing.buttonSize,
          height: AppSpacing.buttonSize,
          fit: BoxFit.cover,
        ),
      );
    }
    return Container(
      width: AppSpacing.buttonSize,
      height: AppSpacing.buttonSize,
      decoration: BoxDecoration(
        color: _fieldBackground(context),
        borderRadius: radius,
      ),
      alignment: Alignment.center,
      child: Icon(
        item.type == ChatInputAttachmentType.image
            ? Icons.image_outlined
            : Icons.insert_drive_file_outlined,
        size: AppSpacing.iconMedium,
        color: _foregroundSecondary(context),
      ),
    );
  }

  Widget _buildVoicePanel() {
    final isPressed = _isRecording;
    final fill = _composerInputFill(context);
    final sepIdle = _separatorColor(context).withValues(alpha: 0.12);
    return ClipRRect(
      borderRadius: BorderRadius.circular(_fieldCornerRadius),
      child: ColoredBox(
        color: fill,
        child: SizedBox(
          height: _composerCenterMinHeight,
          width: double.infinity,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapDown: (_) => _startVoiceRecord(),
            onTapUp: (_) => _stopVoiceRecordAndSend(),
            onTapCancel: () => _stopVoiceRecordAndSend(),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 160),
              curve: Curves.easeOut,
              alignment: Alignment.center,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
              decoration: BoxDecoration(
                color: isPressed
                    ? AppColors.primaryColor.withValues(alpha: 0.1)
                    : Colors.transparent,
                border: Border.all(
                  color: isPressed ? AppColors.primaryColor : sepIdle,
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (isPressed) ...[
                    SizedBox(height: AppSpacing.lg, child: _buildWaveBars()),
                    SizedBox(width: AppSpacing.sm),
                  ],
                  Text(
                    isPressed
                        ? UITextConstants.chatVoiceReleaseToSend
                        : UITextConstants.chatVoiceHoldToTalk,
                    style: _composerTextStyle(context).copyWith(
                      color: isPressed
                          ? AppColors.primaryColor
                          : _foregroundPrimary(context),
                      fontWeight: AppTypography.regular,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildWaveBars() {
    return AnimatedBuilder(
      animation: _waveController,
      builder: (context, _) {
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: _waveBars
              .map((value) {
                final h = 3 + (AppSpacing.md * 0.85 * value);
                return Container(
                  width: AppSpacing.three,
                  height: h,
                  margin: EdgeInsets.symmetric(horizontal: AppSpacing.oneHalf),
                  decoration: BoxDecoration(
                    color: AppColors.primaryColor.withValues(
                      alpha: 0.45 + value * 0.5,
                    ),
                    borderRadius: BorderRadius.circular(AppSpacing.three),
                  ),
                );
              })
              .toList(growable: false),
        );
      },
    );
  }

  int _estimateLineCount({
    required String text,
    required TextStyle style,
    required double maxWidth,
  }) {
    if (text.trim().isEmpty || maxWidth <= 0) {
      return 1;
    }
    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: maxWidth);
    return math.max(1, painter.computeLineMetrics().length);
  }

  Widget _buildTextComposerCenter() {
    final textStyle = _composerTextStyle(context);
    final secondary = _foregroundSecondary(context);
    final hPad = AppSpacing.md;
    return LayoutBuilder(
      builder: (context, constraints) {
        final estimatedWidth = constraints.maxWidth - hPad * 2;
        final lineCount = _estimateLineCount(
          text: _controller.text,
          style: textStyle,
          maxWidth: estimatedWidth,
        );
        final canExpandInline =
            widget.enableExpandedEditor && lineCount > widget.maxVisibleLines;
        final alignVertical = lineCount <= 1
            ? TextAlignVertical.center
            : TextAlignVertical.top;
        final fontSize = textStyle.fontSize ?? AppSpacing.md;
        final lineHeight = textStyle.height ?? AppTypography.bodyLineHeight;
        final lineBoxHeight = fontSize * lineHeight;
        final vPad = lineCount <= 1
            ? ((_composerCenterMinHeight - lineBoxHeight) / 2).clamp(
                AppSpacing.xs,
                AppSpacing.lg,
              )
            : AppSpacing.sm;
        return ClipRRect(
          borderRadius: BorderRadius.circular(_fieldCornerRadius),
          child: ColoredBox(
            color: _composerInputFill(context),
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                minHeight: _composerCenterMinHeight,
              ),
              child: Stack(
                children: [
                  TextField(
                    key: widget.textFieldKey,
                    controller: _controller,
                    focusNode: _focusNode,
                    scrollController: _textScrollController,
                    enabled: !_isVoiceMode,
                    maxLength: widget.maxTextLength,
                    maxLines: widget.maxVisibleLines,
                    minLines: 1,
                    textAlignVertical: alignVertical,
                    cursorColor: AppColors.primaryColor,
                    style: textStyle,
                    strutStyle: StrutStyle(
                      fontSize: fontSize,
                      height: lineHeight,
                      leadingDistribution: TextLeadingDistribution.even,
                      forceStrutHeight: true,
                    ),
                    onTap: () {
                      if (_panelMode != ChatInputPanelMode.none) {
                        setState(() => _panelMode = ChatInputPanelMode.none);
                      }
                    },
                    decoration: InputDecoration(
                      hintText: widget.hintText ?? UITextConstants.inputHint,
                      hintStyle: TextStyle(
                        color: secondary,
                        fontSize: fontSize,
                        height: lineHeight,
                      ),
                      border: InputBorder.none,
                      isDense: true,
                      counterText: '',
                      contentPadding: EdgeInsets.fromLTRB(
                        hPad,
                        vPad,
                        hPad,
                        vPad,
                      ),
                    ),
                  ),
                  if (canExpandInline)
                    Positioned(
                      left: AppSpacing.sm,
                      top: AppSpacing.xs,
                      child: Material(
                        color: Colors.transparent,
                        child: IconButton(
                          key: TestKeys.chatInputExpandButton,
                          onPressed: _openExpandedEditor,
                          padding: EdgeInsets.zero,
                          constraints: BoxConstraints(
                            minWidth: AppSpacing.iconButtonMinSizeSm,
                            minHeight: AppSpacing.iconButtonMinSizeSm,
                          ),
                          alignment: Alignment.centerLeft,
                          icon: Icon(
                            Icons.open_in_full,
                            size: AppSpacing.iconSmall,
                            color: secondary,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildComposerRow() {
    final state = _visualState();
    final actions = _defaultActions();
    final right =
        widget.rightBuilder?.call(context, state, actions) ??
        _buildTrailingButtons(context);
    final left =
        widget.leftBuilder?.call(context, state, actions) ??
        _buildToolbarPlainIconButton(
          context: context,
          key: TestKeys.chatInputVoiceToggleButton,
          icon: _isVoiceMode ? _kChatInputKeyboardCompactIcon : CupertinoIcons.mic,
          onTap: _toggleVoiceMode,
          semanticLabel: _isVoiceMode
              ? UITextConstants.keyboard
              : UITextConstants.voiceInput,
        );
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        left,
        if (left is! SizedBox) SizedBox(width: AppSpacing.sm),
        Expanded(
          child: _isVoiceMode
              ? _buildVoicePanel()
              : _buildTextComposerCenter(),
        ),
        if (right.isNotEmpty) SizedBox(width: AppSpacing.sm),
        Row(mainAxisSize: MainAxisSize.min, children: right),
      ],
    );
  }

  Widget _buildAddPanel() {
    if (!_showAddPanel) return const SizedBox.shrink();
    final disableImage =
        _attachments.isNotEmpty &&
        _attachments.first.type == ChatInputAttachmentType.file;
    final disableFile =
        _attachments.isNotEmpty &&
        _attachments.first.type == ChatInputAttachmentType.image;
    final panelItems = <_PanelActionItem>[
      _PanelActionItem(
        icon: Icons.photo_library_outlined,
        text: UITextConstants.chatMorePhoto,
        disabled: disableImage,
        onTap: _pickImages,
      ),
      _PanelActionItem(
        icon: Icons.camera_alt_outlined,
        text: UITextConstants.chatMoreShoot,
        disabled: disableImage,
        onTap: _capturePhoto,
      ),
      _PanelActionItem(
        icon: Icons.insert_drive_file_outlined,
        text: UITextConstants.chatMoreFile,
        disabled: disableFile,
        onTap: _pickFiles,
      ),
      ...widget.extraPanelItems.map(
        (item) => _PanelActionItem(
          icon: item.icon,
          text: item.text,
          disabled: item.disabled,
          onTap: item.onTap,
        ),
      ),
    ];
    return Container(
      margin: EdgeInsets.only(top: AppSpacing.sm),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.md,
      ),
      decoration: BoxDecoration(
        color: _sheetBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: _separatorColor(context).withValues(alpha: 0.35),
        ),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final columns = panelItems.length < 4 ? panelItems.length : 4;
          final itemWidth =
              (constraints.maxWidth - AppSpacing.sm * (columns - 1)) / columns;
          return Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.md,
            children: panelItems
                .map(
                  (item) => SizedBox(
                    width: itemWidth,
                    child: _buildPanelItem(
                      icon: item.icon,
                      text: item.text,
                      disabled: item.disabled,
                      onTap: item.onTap,
                    ),
                  ),
                )
                .toList(growable: false),
          );
        },
      ),
    );
  }

  Widget _buildPanelItem({
    required IconData icon,
    required String text,
    required bool disabled,
    required Future<void> Function() onTap,
  }) {
    final fg = disabled
        ? _foregroundPrimary(context).withValues(alpha: 0.25)
        : _foregroundPrimary(context).withValues(alpha: 0.78);
    return Semantics(
      button: true,
      enabled: !disabled,
      label: text,
      child: GestureDetector(
        onTap: disabled ? null : onTap,
        child: Container(
          padding: EdgeInsets.symmetric(
            vertical: AppSpacing.md,
            horizontal: AppSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: _fieldBackground(
              context,
            ).withValues(alpha: disabled ? 0.55 : 1),
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: AppSpacing.buttonSize + AppSpacing.md,
                height: AppSpacing.buttonSize + AppSpacing.md,
                decoration: BoxDecoration(
                  color: _sheetBackground(context),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                ),
                alignment: Alignment.center,
                child: Icon(icon, size: AppSpacing.iconLarge, color: fg),
              ),
              SizedBox(height: AppSpacing.sm),
              Text(
                text,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: AppTypography.sm, color: fg),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEmojiPanel() {
    if (!_showEmojiPanel) return const SizedBox.shrink();
    return Container(
      margin: EdgeInsets.only(top: AppSpacing.sm),
      child: UnifiedEmojiPicker(
        showCloseButton: true,
        onClose: () => setState(() => _panelMode = ChatInputPanelMode.none),
        onEmojiSelected: (char) {
          final next = '${_controller.text}$char';
          _controller.value = TextEditingValue(
            text: next,
            selection: TextSelection.collapsed(offset: next.length),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildAttachmentPreview(),
          if (_attachments.isNotEmpty) SizedBox(height: AppSpacing.sm),
          _buildComposerRow(),
          _buildEmojiPanel(),
          _buildAddPanel(),
        ],
      ),
    );
  }
}

class _PanelActionItem {
  const _PanelActionItem({
    required this.icon,
    required this.text,
    required this.disabled,
    required this.onTap,
  });

  final IconData icon;
  final String text;
  final bool disabled;
  final Future<void> Function() onTap;
}

class _ExpandedInputDraft {
  const _ExpandedInputDraft({required this.text, required this.openEmojiPanel});

  final String text;
  final bool openEmojiPanel;
}

class _ExpandedChatInputPage extends StatefulWidget {
  const _ExpandedChatInputPage({
    required this.initialText,
    required this.hintText,
    required this.showEmojiButton,
  });

  final String initialText;
  final String hintText;
  final bool showEmojiButton;

  @override
  State<_ExpandedChatInputPage> createState() => _ExpandedChatInputPageState();
}

class _ExpandedChatInputPageState extends State<_ExpandedChatInputPage> {
  late final TextEditingController _controller;
  final FocusNode _focusNode = FocusNode();
  bool _showEmojiPanel = false;

  Color _cupertinoColor(BuildContext context, CupertinoDynamicColor color) {
    return CupertinoDynamicColor.resolve(color, context);
  }

  Color _foregroundPrimary(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.label);

  Color _foregroundSecondary(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.secondaryLabel);

  Color _surfaceBackground(BuildContext context) => _cupertinoColor(
    context,
    CupertinoColors.secondarySystemGroupedBackground,
  );

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialText);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _focusNode.requestFocus();
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _closeEditor() {
    Navigator.of(context).pop(
      _ExpandedInputDraft(
        text: _controller.text,
        openEmojiPanel: _showEmojiPanel,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final composerFontSize =
        Theme.of(context).textTheme.bodyLarge?.fontSize ?? AppSpacing.md;
    final composerStyle = TextStyle(
      fontSize: composerFontSize,
      height: AppTypography.bodyLineHeight,
      color: _foregroundPrimary(context),
    );
    return CupertinoPageScaffold(
      backgroundColor: _surfaceBackground(context),
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.sm,
                AppSpacing.xs,
                AppSpacing.sm,
                AppSpacing.sm,
              ),
              child: Row(
                children: [
                  CupertinoButton(
                    key: TestKeys.chatInputCollapseButton,
                    padding: EdgeInsets.zero,
                    minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                    onPressed: _closeEditor,
                    child: Icon(
                      CupertinoIcons.chevron_down,
                      color: _foregroundPrimary(context),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Container(
                key: TestKeys.fullscreenModalSurface,
                width: double.infinity,
                margin: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                padding: EdgeInsets.all(AppSpacing.md),
                decoration: BoxDecoration(
                  color: CupertinoColors.systemBackground.resolveFrom(context),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                ),
                child: Material(
                  color: Colors.transparent,
                  child: TextField(
                    controller: _controller,
                    focusNode: _focusNode,
                    maxLines: null,
                    expands: true,
                    textAlignVertical: TextAlignVertical.top,
                    cursorColor: AppColors.primaryColor,
                    style: composerStyle,
                    decoration: InputDecoration(
                      hintText: widget.hintText,
                      hintStyle: composerStyle.copyWith(
                        color: _foregroundSecondary(context),
                      ),
                      border: InputBorder.none,
                    ),
                  ),
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.md,
                AppSpacing.sm,
                AppSpacing.md,
                AppSpacing.sm,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  if (widget.showEmojiButton)
                    CupertinoButton(
                      key: TestKeys.chatInputExpandedEmojiToggleButton,
                      padding: EdgeInsets.zero,
                      minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                      onPressed: () {
                        setState(() => _showEmojiPanel = !_showEmojiPanel);
                        if (_showEmojiPanel) {
                          _focusNode.unfocus();
                        } else {
                          _focusNode.requestFocus();
                        }
                      },
                      child: Icon(
                        _showEmojiPanel
                            ? _kChatInputKeyboardCompactIcon
                            : _kChatInputEmojiPanelIcon,
                        size: _kChatInputToolbarGlyphSize,
                        color: _foregroundPrimary(context)
                            .withValues(alpha: 0.82),
                      ),
                    ),
                ],
              ),
            ),
            if (_showEmojiPanel)
              UnifiedEmojiPicker(
                showCloseButton: false,
                onEmojiSelected: (char) {
                  final next = '${_controller.text}$char';
                  _controller.value = TextEditingValue(
                    text: next,
                    selection: TextSelection.collapsed(offset: next.length),
                  );
                },
              ),
          ],
        ),
      ),
    );
  }
}
