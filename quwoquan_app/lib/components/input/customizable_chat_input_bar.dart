import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum ChatInputAttachmentType { image, file }

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

class ChatInputVisualState {
  const ChatInputVisualState({
    required this.isVoiceMode,
    required this.isRecording,
    required this.hasText,
    required this.hasAttachments,
    required this.showAddPanel,
  });

  final bool isVoiceMode;
  final bool isRecording;
  final bool hasText;
  final bool hasAttachments;
  final bool showAddPanel;
}

class ChatInputDefaultActions {
  const ChatInputDefaultActions({
    required this.toggleVoiceMode,
    required this.toggleAddPanel,
    required this.send,
  });

  final VoidCallback toggleVoiceMode;
  final VoidCallback toggleAddPanel;
  final VoidCallback send;
}

typedef ChatInputLeftBuilder = Widget Function(
  BuildContext context,
  ChatInputVisualState state,
  ChatInputDefaultActions actions,
);

typedef ChatInputRightBuilder = List<Widget> Function(
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
    this.hintText,
    this.maxTextLength = 5000,
    this.maxVisibleLines = 4,
    this.maxAttachmentCount = 3,
    this.initialAttachments = const <ChatInputAttachment>[],
    this.onPickImages,
    this.onPickFiles,
    this.onCapturePhoto,
    this.onRequestMicPermission,
    this.onStartRecord,
    this.onStopRecord,
    this.onVoiceAsrTransform,
    this.leftBuilder,
    this.rightBuilder,
    this.onAttachmentChanged,
    this.onToast,
    this.showAddPanel = true,
  });

  final TextEditingController? controller;
  final FocusNode? focusNode;
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
  final ChatInputLeftBuilder? leftBuilder;
  final ChatInputRightBuilder? rightBuilder;
  final ValueChanged<List<ChatInputAttachment>>? onAttachmentChanged;
  final ValueChanged<String>? onToast;
  final bool showAddPanel;

  @override
  State<CustomizableChatInputBar> createState() => _CustomizableChatInputBarState();
}

class _CustomizableChatInputBarState extends State<CustomizableChatInputBar>
    with SingleTickerProviderStateMixin {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  late final bool _isExternalController;
  late final bool _isExternalFocusNode;
  final List<ChatInputAttachment> _attachments = <ChatInputAttachment>[];

  bool _showAddPanel = false;
  bool _isVoiceMode = false;
  bool _isRecording = false;
  DateTime? _recordStartAt;

  late final AnimationController _waveController;
  final List<double> _waveBars = List<double>.filled(24, 0.2);
  Timer? _waveTicker;

  bool get _hasText => _controller.text.trim().isNotEmpty;
  bool get _hasAttachments => _attachments.isNotEmpty;
  bool get _canSend => _hasText || _hasAttachments;

  ChatInputVisualState get _visualState => ChatInputVisualState(
    isVoiceMode: _isVoiceMode,
    isRecording: _isRecording,
    hasText: _hasText,
    hasAttachments: _hasAttachments,
    showAddPanel: _showAddPanel,
  );

  ChatInputDefaultActions get _defaultActions => ChatInputDefaultActions(
    toggleVoiceMode: _toggleVoiceMode,
    toggleAddPanel: _toggleAddPanel,
    send: _send,
  );

  @override
  void initState() {
    super.initState();
    _isExternalController = widget.controller != null;
    _isExternalFocusNode = widget.focusNode != null;
    _controller = widget.controller ?? TextEditingController();
    _focusNode = widget.focusNode ?? FocusNode();
    _attachments.addAll(widget.initialAttachments);
    _controller.addListener(_onTextChanged);
    _waveController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _waveTicker?.cancel();
    _waveController.dispose();
    _controller.removeListener(_onTextChanged);
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

  void _emitToast(String text) {
    if (widget.onToast != null) {
      widget.onToast!(text);
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(text)));
  }

  bool _acceptAttachmentType(ChatInputAttachmentType type) {
    if (_attachments.isEmpty) return true;
    final existingType = _attachments.first.type;
    if (existingType == type) return true;
    _emitToast(UITextConstants.chatAttachmentTypeConflict);
    return false;
  }

  int get _remainingAttachmentCount => math.max(
    0,
    widget.maxAttachmentCount - _attachments.length,
  );

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
    widget.onAttachmentChanged?.call(List<ChatInputAttachment>.from(_attachments));
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
    widget.onAttachmentChanged?.call(List<ChatInputAttachment>.from(_attachments));
  }

  void _toggleAddPanel() {
    if (!widget.showAddPanel || _isVoiceMode) return;
    setState(() {
      _showAddPanel = !_showAddPanel;
      if (_showAddPanel) {
        _focusNode.unfocus();
      }
    });
  }

  void _toggleVoiceMode() {
    setState(() {
      _isVoiceMode = !_isVoiceMode;
      _showAddPanel = false;
      _focusNode.unfocus();
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
    await widget.onSend(payload);
    if (!mounted) return;
    setState(() {
      _controller.clear();
      _attachments.clear();
      _showAddPanel = false;
    });
    widget.onAttachmentChanged?.call(const <ChatInputAttachment>[]);
  }

  Future<void> _startVoiceRecord() async {
    if (_isRecording) return;
    final hasPermission = await (widget.onRequestMicPermission?.call() ?? Future<bool>.value(true));
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
    _waveTicker?.cancel();
    _waveTicker = Timer.periodic(const Duration(milliseconds: 56), (_) {
      if (!mounted || !_isRecording) return;
      setState(() {
        for (var i = 0; i < _waveBars.length; i++) {
          final seed = (DateTime.now().millisecondsSinceEpoch / 1000) + i * 0.23;
          final base = (math.sin(seed * 4.2) + 1) / 2;
          _waveBars[i] = 0.15 + base * 0.85;
        }
      });
    });
  }

  void _stopWave() {
    _waveTicker?.cancel();
    _waveTicker = null;
    setState(() {
      for (var i = 0; i < _waveBars.length; i++) {
        _waveBars[i] = 0.2;
      }
    });
  }

  Widget _defaultLeftButton(BuildContext context) {
    if (_isVoiceMode || _hasText || _hasAttachments) {
      return const SizedBox.shrink();
    }
    return _buildIconButton(
      icon: Icons.camera_alt_outlined,
      onTap: _capturePhoto,
    );
  }

  List<Widget> _defaultRightButtons(BuildContext context) {
    if (_isVoiceMode) return const <Widget>[];
    if (_canSend) {
      return <Widget>[
        _buildIconButton(
          icon: Icons.add,
          onTap: _toggleAddPanel,
        ),
        SizedBox(width: AppSpacing.xs),
        _buildSendButton(),
      ];
    }
    return <Widget>[
      _buildIconButton(
        icon: Icons.mic_none,
        onTap: _toggleVoiceMode,
      ),
      SizedBox(width: AppSpacing.xs),
      _buildIconButton(
        icon: Icons.add,
        onTap: _toggleAddPanel,
      ),
    ];
  }

  Widget _buildIconButton({
    required IconData icon,
    required VoidCallback onTap,
  }) {
    return SizedBox(
      width: AppSpacing.iconButtonMinSizeSm,
      height: AppSpacing.iconButtonMinSizeSm,
      child: IconButton(
        onPressed: onTap,
        icon: Icon(icon, size: AppSpacing.iconMedium),
        color: Colors.black.withValues(alpha: 0.8),
        padding: EdgeInsets.zero,
        constraints: const BoxConstraints(),
      ),
    );
  }

  Widget _buildSendButton() {
    return GestureDetector(
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
          size: AppSpacing.iconMedium,
          color: Colors.white,
        ),
      ),
    );
  }

  Widget _buildAttachmentPreview() {
    if (_attachments.isEmpty) return const SizedBox.shrink();
    return SizedBox(
      height: AppSpacing.buttonSize + AppSpacing.sm,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        child: Row(
          children: _attachments.map((item) {
            final bg = item.type == ChatInputAttachmentType.image
                ? Colors.grey.withValues(alpha: 0.16)
                : Colors.grey.withValues(alpha: 0.12);
            return Container(
              width: AppSpacing.twoHundredTwenty,
              margin: EdgeInsets.only(right: AppSpacing.sm),
              padding: EdgeInsets.all(AppSpacing.sm),
              decoration: BoxDecoration(
                color: bg,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
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
                            color: Colors.black.withValues(alpha: 0.85),
                          ),
                        ),
                        if ((item.subtitle ?? '').trim().isNotEmpty)
                          Text(
                            item.subtitle!,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              color: Colors.black.withValues(alpha: 0.5),
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
                        color: Colors.black.withValues(alpha: 0.6),
                      ),
                    ),
                  ),
                ],
              ),
            );
          }).toList(growable: false),
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
        color: Colors.white.withValues(alpha: 0.85),
        borderRadius: radius,
      ),
      alignment: Alignment.center,
      child: Icon(
        item.type == ChatInputAttachmentType.image
            ? Icons.image_outlined
            : Icons.insert_drive_file_outlined,
        size: AppSpacing.iconMedium,
        color: Colors.black.withValues(alpha: 0.65),
      ),
    );
  }

  Widget _buildVoicePanel() {
    final isPressed = _isRecording;
    final topHint = isPressed
        ? UITextConstants.chatVoiceReleaseToSend
        : UITextConstants.chatVoiceHoldTip;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          height: AppSpacing.md + AppSpacing.xs,
          child: Center(
            child: Text(
              topHint,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColors.primaryColor.withValues(alpha: 0.9),
              ),
            ),
          ),
        ),
        SizedBox(
          height: AppSpacing.buttonSize - AppSpacing.xs,
          child: _buildWaveBars(),
        ),
        SizedBox(height: AppSpacing.xs),
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: _toggleVoiceMode,
          onTapDown: (_) => _startVoiceRecord(),
          onTapUp: (_) => _stopVoiceRecordAndSend(),
          onTapCancel: () => _stopVoiceRecordAndSend(),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            curve: Curves.easeOut,
            width: double.infinity,
            height: AppSpacing.buttonHeight,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: isPressed
                  ? AppColors.primaryColor
                  : AppColors.primaryColor.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius * 2),
            ),
            child: Text(
              UITextConstants.chatVoiceHoldToTalk,
              style: TextStyle(
                color: isPressed ? Colors.white : AppColors.primaryColor,
                fontSize: AppTypography.base,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildWaveBars() {
    return AnimatedBuilder(
      animation: _waveController,
      builder: (context, _) {
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: _waveBars.map((value) {
            final h = 4 + (AppSpacing.buttonSize * 0.7 * value);
            return Container(
              width: AppSpacing.three,
              height: h,
              margin: EdgeInsets.symmetric(horizontal: AppSpacing.oneHalf),
              decoration: BoxDecoration(
                color: AppColors.primaryColor.withValues(alpha: 0.45 + value * 0.5),
                borderRadius: BorderRadius.circular(AppSpacing.three),
              ),
            );
          }).toList(growable: false),
        );
      },
    );
  }

  Widget _buildInputRow() {
    final left = widget.leftBuilder?.call(context, _visualState, _defaultActions) ??
        _defaultLeftButton(context);
    final right =
        widget.rightBuilder?.call(context, _visualState, _defaultActions) ??
            _defaultRightButtons(context);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius * 2),
        boxShadow: [
          BoxShadow(
            blurRadius: AppSpacing.xs,
            color: Colors.black.withValues(alpha: 0.06),
          ),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          left,
          if (left is! SizedBox) SizedBox(width: AppSpacing.xs),
          Expanded(
            child: TextField(
              controller: _controller,
              focusNode: _focusNode,
              enabled: !_isVoiceMode,
              maxLength: widget.maxTextLength,
              maxLines: widget.maxVisibleLines,
              minLines: 1,
              style: TextStyle(
                fontSize: AppTypography.base,
                color: Colors.black.withValues(alpha: 0.88),
              ),
              decoration: InputDecoration(
                hintText: widget.hintText ?? UITextConstants.inputHint,
                border: InputBorder.none,
                isDense: true,
                counterText: '',
                contentPadding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.xs,
                  vertical: AppSpacing.sm,
                ),
              ),
            ),
          ),
          if (right.isNotEmpty) SizedBox(width: AppSpacing.xs),
          ...right,
        ],
      ),
    );
  }

  Widget _buildAddPanel() {
    if (!_showAddPanel || _isVoiceMode) return const SizedBox.shrink();
    final disableImage = _attachments.isNotEmpty &&
        _attachments.first.type == ChatInputAttachmentType.file;
    final disableFile = _attachments.isNotEmpty &&
        _attachments.first.type == ChatInputAttachmentType.image;
    return Container(
      margin: EdgeInsets.only(top: AppSpacing.sm),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Row(
        children: [
          _buildPanelItem(
            icon: Icons.photo_library_outlined,
            text: UITextConstants.chatMorePhoto,
            disabled: disableImage,
            onTap: _pickImages,
          ),
          SizedBox(width: AppSpacing.sm),
          _buildPanelItem(
            icon: Icons.camera_alt_outlined,
            text: UITextConstants.chatMoreShoot,
            disabled: disableImage,
            onTap: _capturePhoto,
          ),
          SizedBox(width: AppSpacing.sm),
          _buildPanelItem(
            icon: Icons.insert_drive_file_outlined,
            text: UITextConstants.chatMoreFile,
            disabled: disableFile,
            onTap: _pickFiles,
          ),
        ],
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
        ? Colors.black.withValues(alpha: 0.25)
        : Colors.black.withValues(alpha: 0.75);
    return Expanded(
      child: GestureDetector(
        onTap: disabled ? null : onTap,
        child: Container(
          padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: disabled ? 0.03 : 0.05),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: AppSpacing.iconLarge, color: fg),
              SizedBox(height: AppSpacing.xs),
              Text(
                text,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: fg,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildAttachmentPreview(),
        if (_attachments.isNotEmpty) SizedBox(height: AppSpacing.sm),
        if (_isVoiceMode) _buildVoicePanel() else _buildInputRow(),
        _buildAddPanel(),
      ],
    );
  }
}
