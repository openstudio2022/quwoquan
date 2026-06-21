import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart' show MaxLengthEnforcement;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart'
    show CommentDto;
import 'package:quwoquan_app/components/comment_system/comment_composer_models.dart';
import 'package:quwoquan_app/components/comment_system/comment_draft_store.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

/// 评论统一输入浮层。
///
/// 三种评论宿主（侵入式分屏 / 内容平铺 / 卡片弹窗）点击「说点什么…」或回复时
/// 都通过 [CommentInputOverlay.show] 弹出同一套输入态：顶部多行输入框（两行起、
/// 最多五行后内部滚动）+ 工具行（语音 / 图片 / @ / emoji / 更多 + 发送）+
/// 最近 emoji 横条 / emoji 面板，键盘顶起且输入框贴键盘上方。
///
/// 全程使用 Cupertino 组件（`CupertinoTextField` / `CupertinoButton`），不依赖
/// Material 祖先，彻底规避「TextField 缺少 Material 祖先」在沉浸式壳下崩溃的问题。
class CommentInputOverlay {
  const CommentInputOverlay._();

  /// 弹出统一评论输入态。提交成功返回 `true`。
  static Future<bool> show(
    BuildContext context, {
    required String postId,
    CommentConfig config = const CommentConfig(),
    CommentDto? replyTo,
    String surfaceMode = 'overlay',
    List<CommentMentionCandidate> mentionCandidates = _defaultMentions,
    FutureOr<void> Function(CommentComposerPayload payload)? onSubmit,
  }) async {
    final result = await showCupertinoModalPopup<bool>(
      context: context,
      barrierColor: AppColors.transparent,
      builder: (ctx) => _CommentInputSheet(
        postId: postId,
        config: config,
        replyTo: replyTo,
        surfaceMode: surfaceMode,
        mentionCandidates: mentionCandidates,
        onSubmit: onSubmit,
      ),
    );
    return result ?? false;
  }

  static const List<CommentMentionCandidate> _defaultMentions =
      <CommentMentionCandidate>[
        CommentMentionCandidate(
          subjectType: 'assistant',
          subjectId: 'assistant_xiaoqu',
          displayName: UITextConstants.assistantEntryXiaoqu,
        ),
      ];
}

class _CommentInputSheet extends ConsumerStatefulWidget {
  const _CommentInputSheet({
    required this.postId,
    required this.config,
    required this.surfaceMode,
    required this.mentionCandidates,
    this.replyTo,
    this.onSubmit,
  });

  final String postId;
  final CommentConfig config;
  final CommentDto? replyTo;
  final String surfaceMode;
  final List<CommentMentionCandidate> mentionCandidates;
  final FutureOr<void> Function(CommentComposerPayload payload)? onSubmit;

  @override
  ConsumerState<_CommentInputSheet> createState() => _CommentInputSheetState();
}

class _CommentInputSheetState extends ConsumerState<_CommentInputSheet> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  final List<CommentMentionCandidate> _selectedMentions =
      <CommentMentionCandidate>[];
  final List<String> _attachmentMediaIds = <String>[];

  late CommentConfig _effectiveConfig;
  bool _showEmojiPanel = false;
  bool _isUploadingAttachment = false;
  bool _isSubmitting = false;
  bool _draftCleared = false;
  Timer? _draftSaveTimer;

  @override
  void initState() {
    super.initState();
    _effectiveConfig = ref
        .read(commentRemoteConfigProvider)
        .toComposerConfig(fallbackConfig: widget.config);
    _controller.addListener(_onTextChanged);
    // 输入态曝光：运营漏斗起点（区分回复 vs 顶层评论、来源宿主）。
    ref
        .read(commentObservabilityProvider)
        .trackAction(
          eventName: CommentEventNames.surfaceExpose,
          postId: widget.postId,
          surfaceMode: widget.surfaceMode,
          replyDepth: widget.replyTo == null ? 0 : 1,
        );
    unawaited(_restoreDraft());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _focusNode.requestFocus();
    });
  }

  /// 续写本帖/本回复目标的未发草稿（仅在用户尚未输入、且无待续接登录文本时回灌）。
  Future<void> _restoreDraft() async {
    final draft = await CommentDraftStore.load(
      widget.postId,
      replyToCommentId: widget.replyTo?.id,
    );
    if (draft == null || !mounted) return;
    if (_controller.text.isNotEmpty || _attachmentMediaIds.isNotEmpty) return;
    setState(() {
      _controller.text = draft.content;
      _controller.selection = TextSelection.collapsed(
        offset: _controller.text.length,
      );
      _attachmentMediaIds
        ..clear()
        ..addAll(draft.attachmentMediaIds);
      for (final subjectId in draft.mentionSubjectIds) {
        final candidate = widget.mentionCandidates
            .where((c) => c.subjectId == subjectId)
            .toList(growable: false);
        if (candidate.isNotEmpty &&
            !_selectedMentions.any((m) => m.subjectId == subjectId)) {
          _selectedMentions.add(candidate.first);
        }
      }
    });
  }

  void _scheduleDraftSave() {
    if (_draftCleared) return;
    _draftSaveTimer?.cancel();
    _draftSaveTimer = Timer(const Duration(milliseconds: 300), _persistDraft);
  }

  void _persistDraft() {
    if (_draftCleared) return;
    unawaited(
      CommentDraftStore.save(
        widget.postId,
        replyToCommentId: widget.replyTo?.id,
        draft: CommentDraft(
          content: _controller.text,
          attachmentMediaIds: List<String>.unmodifiable(_attachmentMediaIds),
          mentionSubjectIds: _selectedMentions
              .map((m) => m.subjectId)
              .toList(growable: false),
        ),
      ),
    );
  }

  void _clearDraft() {
    _draftCleared = true;
    _draftSaveTimer?.cancel();
    unawaited(
      CommentDraftStore.clear(
        widget.postId,
        replyToCommentId: widget.replyTo?.id,
      ),
    );
  }

  @override
  void dispose() {
    _draftSaveTimer?.cancel();
    // 关闭未提交：立即落盘当前草稿，重新打开同目标输入态可续写。
    if (!_draftCleared) {
      _persistDraft();
    }
    _controller.removeListener(_onTextChanged);
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _onTextChanged() {
    setState(() {});
    _scheduleDraftSave();
  }

  bool get _canSend =>
      _controller.text.trim().isNotEmpty &&
      !_isSubmitting &&
      _effectiveConfig.canUserComment;

  String _hintText() {
    if (!_effectiveConfig.canUserComment) {
      final loggedIn = ref.read(authSessionControllerProvider).isAuthenticated;
      return loggedIn
          ? UITextConstants.commentClosed
          : UITextConstants.needLogin;
    }
    final replyTo = widget.replyTo;
    if (replyTo != null) {
      return UITextConstants.commentReplyToTemplate.replaceFirst(
        '%s',
        replyTo.displayName ?? replyTo.authorId,
      );
    }
    return UITextConstants.commentPlaceholder;
  }

  void _insertText(String text) {
    final selection = _controller.selection;
    final current = _controller.text;
    final offset = selection.isValid
        ? selection.baseOffset.clamp(0, current.length)
        : current.length;
    final next =
        current.substring(0, offset) + text + current.substring(offset);
    _controller
      ..text = next
      ..selection = TextSelection.collapsed(offset: offset + text.length);
  }

  void _toggleEmojiPanel() {
    setState(() {
      _showEmojiPanel = !_showEmojiPanel;
      if (_showEmojiPanel) {
        _focusNode.unfocus();
      } else {
        _focusNode.requestFocus();
      }
    });
  }

  void _addMention(CommentMentionCandidate candidate) {
    final exists = _selectedMentions.any(
      (item) => item.subjectId == candidate.subjectId,
    );
    if (!exists) {
      _selectedMentions.add(candidate);
      ref
          .read(commentObservabilityProvider)
          .trackAction(
            eventName: CommentEventNames.mentionAdded,
            postId: widget.postId,
            mentionCount: _selectedMentions.length,
          );
    }
    _insertText('${UITextConstants.commentMention}${candidate.displayName} ');
    if (_showEmojiPanel) {
      setState(() => _showEmojiPanel = false);
    }
    _focusNode.requestFocus();
  }

  Future<void> _addImageAttachment() async {
    if (_attachmentMediaIds.length >= _effectiveConfig.maxImageAttachments) {
      AppToast.show(
        context,
        UITextConstants.commentAttachmentLimitReachedTemplate.replaceFirst(
          '%s',
          '${_effectiveConfig.maxImageAttachments}',
        ),
      );
      return;
    }
    setState(() => _isUploadingAttachment = true);
    try {
      final repo = ref.read(contentRepositoryProvider);
      final init = await repo.initMediaUpload(mediaType: 'image');
      final completed = await repo.completeMediaUpload(
        sessionId: init.sessionId,
      );
      final mediaId = completed.assetId ?? init.mediaId;
      if (mediaId == null || mediaId.isEmpty) {
        throw StateError('comment media upload returned empty mediaId');
      }
      if (!mounted) return;
      setState(() => _attachmentMediaIds.add(mediaId));
      _scheduleDraftSave();
      ref
          .read(commentObservabilityProvider)
          .trackAction(
            eventName: CommentEventNames.attachmentAdded,
            postId: widget.postId,
            attachmentCount: _attachmentMediaIds.length,
          );
    } catch (e) {
      if (!mounted) return;
      await _showActionError(e);
    } finally {
      if (mounted) setState(() => _isUploadingAttachment = false);
    }
  }

  Future<void> _showActionError(Object error) async {
    if (!mounted) return;
    await AppActionErrorFeedback.show(
      context,
      semantic: runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      ),
    );
  }

  CommentComposerPayload _buildPayload() {
    final maxImages = _effectiveConfig.maxImageAttachments;
    final safeAttachments = _attachmentMediaIds
        .take(maxImages)
        .toList(growable: false);
    return CommentComposerPayload(
      content: _controller.text.trim(),
      attachmentMediaIds: List<String>.unmodifiable(safeAttachments),
      mentions: List<CommentMentionCandidate>.unmodifiable(_selectedMentions),
    );
  }

  void _submit() {
    final content = _controller.text.trim();
    if (content.isEmpty || _isSubmitting) return;
    if (content.length > _effectiveConfig.maxLength) {
      AppToast.show(context, UITextConstants.commentTooLong);
      return;
    }
    if (_attachmentMediaIds.length > _effectiveConfig.maxImageAttachments) {
      AppToast.show(
        context,
        UITextConstants.commentAttachmentLimitReachedTemplate.replaceFirst(
          '%s',
          '${_effectiveConfig.maxImageAttachments}',
        ),
      );
      return;
    }

    // 评论需要账号身份：未登录先登记待续接评论（保留全部草稿），再经统一拦截器
    // 引导登录；本浮层保持挂载并监听登录态翻转，登录成功后在原浮层自动续提。
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      ref
          .read(authContinuationProvider.notifier)
          .set(
            SubmitCommentContinuation(
              content: content,
              postId: widget.postId,
              replyToCommentId: widget.replyTo?.id,
              attachmentMediaIds: List<String>.unmodifiable(
                _attachmentMediaIds,
              ),
              mentions: _selectedMentions
                  .map((candidate) => candidate.toWire())
                  .toList(growable: false),
            ),
          );
      unawaited(requireLogin(ref, context, AuthGateReason.comment));
      return;
    }

    unawaited(_performSubmit());
  }

  /// 登录态翻转为已认证时，消费本帖待续接评论并在原浮层自动续提。
  void _maybeResumeContinuation() {
    if (_isSubmitting) return;
    if (!ref.read(authSessionControllerProvider).isAuthenticated) return;
    final pending = ref
        .read(authContinuationProvider.notifier)
        .take<SubmitCommentContinuation>();
    if (pending == null) return;
    // 续接帖与本浮层不一致：放回槽位，交由对应宿主续接。
    if (pending.postId != null && pending.postId != widget.postId) {
      ref.read(authContinuationProvider.notifier).set(pending);
      return;
    }
    _controller.text = pending.content;
    unawaited(_performSubmit());
  }

  Future<void> _performSubmit() async {
    if (_isSubmitting) return;
    setState(() => _isSubmitting = true);
    final payload = _buildPayload();
    // 宿主自定义 onSubmit 路径绕过了 commentProvider.addComment 内置的提交埋点，
    // 故仅在该路径由浮层补提交成功/失败动作埋点；走 provider 时不重复打点。
    final usesCustomSubmit = widget.onSubmit != null;
    final observability = ref.read(commentObservabilityProvider);
    try {
      if (usesCustomSubmit) {
        await Future<void>.sync(() => widget.onSubmit!(payload));
        observability.trackAction(
          eventName: CommentEventNames.submitSucceeded,
          postId: widget.postId,
          surfaceMode: widget.surfaceMode,
          replyDepth: widget.replyTo == null ? 0 : 1,
          attachmentCount: payload.attachmentMediaIds.length,
          mentionCount: payload.mentions.length,
        );
      } else {
        await ref
            .read(commentProviderFamily(widget.postId).notifier)
            .addComment(
              payload.content,
              replyToCommentId: widget.replyTo?.id,
              attachmentMediaIds: payload.attachmentMediaIds,
              mentions: payload.mentions,
            );
      }
      // 提交成功：清除本目标草稿，避免下次打开回灌已发内容。
      _clearDraft();
      if (!mounted) return;
      // 提交成功即关闭输入态；评论区列表由 provider 乐观插入即时呈现刚发的内容，
      // 用户立刻看到结果，无需额外 toast（避免与列表反馈重复）。
      Navigator.of(context).pop(true);
      return;
    } catch (e) {
      if (usesCustomSubmit) {
        observability.trackAction(
          eventName: CommentEventNames.submitFailed,
          postId: widget.postId,
          surfaceMode: widget.surfaceMode,
          replyDepth: widget.replyTo == null ? 0 : 1,
          failureKind: e.runtimeType.toString(),
        );
      }
      if (!mounted) return;
      setState(() => _isSubmitting = false);
      await _showActionError(e);
    }
  }

  void _dismiss() => Navigator.of(context).maybePop(false);

  @override
  Widget build(BuildContext context) {
    // 监听登录态：游客提交评论引导登录后，回到本浮层自动续提原文本。
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      previous,
      next,
    ) {
      final wasAuthed = previous?.isAuthenticated ?? false;
      if (!wasAuthed && next.isAuthenticated) {
        _maybeResumeContinuation();
      }
    });

    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );

    // 统一用 Cupertino 组件树（CupertinoTextField + CupertinoButton），不依赖
    // Material 祖先，彻底规避「No Material widget found」在沉浸式壳下崩溃。
    // 顶层注入 DefaultTextStyle（带 decoration: none），杜绝 Cupertino modal 路由下
    // 未显式着色的 Text 回退到引擎默认的「红字 + 黄色下划线」。
    return DefaultTextStyle(
      style: TextStyle(
        fontSize: AppTypography.body,
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.foregroundPrimary,
        ),
        decoration: TextDecoration.none,
      ),
      child: GestureDetector(
        key: TestKeys.commentInputOverlayScrim,
        behavior: HitTestBehavior.opaque,
        onTap: _dismiss,
        child: ColoredBox(
          color: AppColorsFunctional.getColor(isDark, ColorType.modalScrim),
          child: Column(
            children: [
              const Spacer(),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {},
                child: Container(
                  key: TestKeys.commentInputOverlay,
                  decoration: BoxDecoration(
                    color: surface,
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(AppSpacing.largeBorderRadius),
                    ),
                  ),
                  padding: EdgeInsets.only(bottom: keyboardInset),
                  child: SafeArea(
                    top: false,
                    bottom: keyboardInset <= 0,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (widget.replyTo != null)
                          _ReplyIndicator(
                            isDark: isDark,
                            username:
                                widget.replyTo!.displayName ??
                                widget.replyTo!.authorId,
                            onCancel: _dismiss,
                          ),
                        _buildEditor(isDark),
                        _buildToolRow(isDark),
                        _buildAccessory(isDark),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEditor(bool isDark) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.sm,
      ),
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.md,
        ),
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.backgroundSecondary,
          ),
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.borderPrimary,
            ).withValues(alpha: 0.5),
            width: AppSpacing.hairline,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            ConstrainedBox(
              constraints: const BoxConstraints(
                minHeight: AppSpacing.commentComposerMinHeight,
                maxHeight: AppSpacing.commentComposerMaxHeight,
              ),
              child: CupertinoTextField(
                key: TestKeys.commentTextField,
                controller: _controller,
                focusNode: _focusNode,
                enabled: _effectiveConfig.canUserComment && !_isSubmitting,
                autofocus: false,
                minLines: 2,
                maxLines: 5,
                maxLength: _effectiveConfig.maxLength,
                maxLengthEnforcement: MaxLengthEnforcement.enforced,
                textInputAction: TextInputAction.newline,
                placeholder: _hintText(),
                placeholderStyle: TextStyle(
                  fontSize: AppTypography.body,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundTertiary,
                  ),
                ),
                style: TextStyle(
                  fontSize: AppTypography.body,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundPrimary,
                  ),
                ),
                decoration: const BoxDecoration(),
                padding: EdgeInsets.zero,
              ),
            ),
            if (_attachmentMediaIds.isNotEmpty) ...[
              SizedBox(height: AppSpacing.sm),
              _AttachmentThumbnail(
                mediaId: _attachmentMediaIds.first,
                isDark: isDark,
                onRemove: () {
                  setState(_attachmentMediaIds.clear);
                  _scheduleDraftSave();
                },
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildToolRow(bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.xs,
      ),
      child: Row(
        children: [
          _ToolIcon(
            icon: CupertinoIcons.photo,
            isDark: isDark,
            busy: _isUploadingAttachment,
            semanticLabel: UITextConstants.commentAttachImage,
            onTap: _isUploadingAttachment ? null : _addImageAttachment,
          ),
          SizedBox(width: AppSpacing.md),
          _ToolIcon(
            key: TestKeys.commentAtXiaoquButton,
            icon: CupertinoIcons.at,
            isDark: isDark,
            semanticLabel: UITextConstants.commentMention,
            onTap: () {
              if (widget.mentionCandidates.isNotEmpty) {
                _addMention(widget.mentionCandidates.first);
              }
            },
          ),
          SizedBox(width: AppSpacing.md),
          _ToolIcon(
            icon: _showEmojiPanel
                ? CupertinoIcons.keyboard
                : CupertinoIcons.smiley,
            isDark: isDark,
            active: _showEmojiPanel,
            semanticLabel: UITextConstants.emojiRecent,
            onTap: _toggleEmojiPanel,
          ),
          const Spacer(),
          _buildCharCounter(isDark),
          SizedBox(width: AppSpacing.sm),
          _SendButton(canSend: _canSend, onTap: _canSend ? _submit : null),
        ],
      ),
    );
  }

  /// 字数计数：仅在已输入时显示「当前/上限」，临近上限转警示色。
  Widget _buildCharCounter(bool isDark) {
    final length = _controller.text.characters.length;
    if (length == 0) {
      return const SizedBox.shrink();
    }
    final maxLength = _effectiveConfig.maxLength;
    final nearLimit = length >= (maxLength * 0.9).floor();
    return Text(
      '$length/$maxLength',
      key: TestKeys.commentCharCounter,
      style: TextStyle(
        fontSize: AppTypography.xs,
        color: nearLimit
            ? AppColors.error
            : AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundTertiary,
              ),
      ),
    );
  }

  Widget _buildAccessory(bool isDark) {
    if (_showEmojiPanel) {
      return UnifiedEmojiPicker(onEmojiSelected: _insertText);
    }
    return _RecentEmojiStrip(isDark: isDark, onSelected: _insertText);
  }
}

class _ReplyIndicator extends StatelessWidget {
  const _ReplyIndicator({
    required this.isDark,
    required this.username,
    required this.onCancel,
  });

  final bool isDark;
  final String username;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.md,
        0,
      ),
      child: Row(
        children: [
          Icon(
            CupertinoIcons.arrowshape_turn_up_left,
            size: AppSpacing.iconSmall,
            color: AppColors.primaryColor,
          ),
          SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Text(
              '${UITextConstants.replyAction} @$username',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColors.primaryColor,
              ),
            ),
          ),
          GestureDetector(
            onTap: onCancel,
            child: Icon(
              CupertinoIcons.xmark,
              size: AppSpacing.iconSmall,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundTertiary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ToolIcon extends StatelessWidget {
  const _ToolIcon({
    super.key,
    required this.icon,
    required this.isDark,
    required this.semanticLabel,
    this.onTap,
    this.active = false,
    this.busy = false,
  });

  final IconData icon;
  final bool isDark;
  final String semanticLabel;
  final VoidCallback? onTap;
  final bool active;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: SizedBox(
        width: AppSpacing.minInteractiveSize,
        height: AppSpacing.minInteractiveSize,
        child: Center(
          child: busy
              ? const CupertinoActivityIndicator()
              : Icon(
                  icon,
                  size: AppSpacing.appChromeActionIconSize,
                  semanticLabel: semanticLabel,
                  color: active
                      ? AppColors.primaryColor
                      : AppColorsFunctional.getColor(
                          isDark,
                          ColorType.foregroundSecondary,
                        ),
                ),
        ),
      ),
    );
  }
}

class _SendButton extends StatelessWidget {
  const _SendButton({required this.canSend, this.onTap});

  final bool canSend;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      key: TestKeys.submitCommentButton,
      padding: EdgeInsets.zero,
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: canSend
              ? AppColors.primaryColor
              : AppColors.primaryColor.withValues(alpha: 0.4),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        ),
        child: Text(
          UITextConstants.commentSend,
          style: TextStyle(
            fontSize: AppTypography.body,
            fontWeight: AppTypography.semiBold,
            color: AppColors.white,
          ),
        ),
      ),
    );
  }
}

/// 输入框底部的单张图片缩略图（右上角可删除），形态参考主流评论输入。
class _AttachmentThumbnail extends StatelessWidget {
  const _AttachmentThumbnail({
    required this.mediaId,
    required this.isDark,
    required this.onRemove,
  });

  final String mediaId;
  final bool isDark;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final thumbnailUrl = 'media/comment/$mediaId/v1/comment.png';
    return SizedBox(
      width: AppSpacing.commentAttachmentThumbnailSize,
      height: AppSpacing.commentAttachmentThumbnailSize,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
            child: Container(
              width: AppSpacing.commentAttachmentThumbnailSize,
              height: AppSpacing.commentAttachmentThumbnailSize,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.backgroundPrimary,
              ),
              alignment: Alignment.center,
              child: AppCachedNetworkImage(
                imageUrl: thumbnailUrl,
                fit: BoxFit.cover,
                width: AppSpacing.commentAttachmentThumbnailSize,
                height: AppSpacing.commentAttachmentThumbnailSize,
                cdnPreset: CdnImagePreset.thumbnail,
                errorWidget: Icon(
                  CupertinoIcons.photo,
                  size: AppSpacing.iconMedium,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundTertiary,
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            top: -AppSpacing.xs,
            right: -AppSpacing.xs,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onRemove,
              child: Container(
                decoration: const BoxDecoration(
                  color: AppColors.overlayStrong,
                  shape: BoxShape.circle,
                ),
                padding: EdgeInsets.all(AppSpacing.xs),
                child: Icon(
                  CupertinoIcons.xmark,
                  size: AppSpacing.iconXSmall,
                  color: AppColors.white,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 最近常用 emoji 横条（无最近记录时不展示）。
class _RecentEmojiStrip extends ConsumerWidget {
  const _RecentEmojiStrip({required this.isDark, required this.onSelected});

  final bool isDark;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final recent = ref
        .watch(emojiRepositoryProvider)
        .when(
          data: (repo) => repo.getRecentEntries(),
          loading: () => const <EmojiEntry>[],
          error: (_, _) => const <EmojiEntry>[],
        );
    if (recent.isEmpty) {
      return const SizedBox.shrink();
    }
    return SizedBox(
      key: TestKeys.commentRecentEmojiStrip,
      height: AppSpacing.commentComposerRecentEmojiHeight,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        itemCount: recent.length,
        separatorBuilder: (_, _) => SizedBox(width: AppSpacing.sm),
        itemBuilder: (context, index) {
          final entry = recent[index];
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => onSelected(entry.char),
            child: Center(
              child: Text(
                entry.char,
                style: const TextStyle(fontSize: AppTypography.xxl),
              ),
            ),
          );
        },
      ),
    );
  }
}
