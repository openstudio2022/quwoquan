import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart' show MaxLengthEnforcement;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_upload_service.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/public/comment_remote_config.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/image_pick_source.dart';
import 'package:quwoquan_app/service/content_service/content/comment/domain/comment_composer_models.dart';
import 'package:quwoquan_app/service/content_service/content/comment/adapters/comment_draft_store.dart';
import 'package:quwoquan_app/service/content_service/content/comment/domain/comment_models.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/emoji/emoji_catalog.dart'
    show EmojiEntry;
import 'package:quwoquan_app/design_system/emoji/emoji_providers.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/observability/trackers/comment_observability.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/chat/unified_emoji_picker.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/comment_provider.dart';
import 'package:quwoquan_app/service/content_service/content/comment/domain/comment_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'comment_input_overlay_components.dart';

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
    required AppUiSurface sourceSurface,
    CommentConfig config = const CommentConfig(),
    CommentViewData? replyTo,
    String surfaceMode = 'overlay',
    List<CommentMention>? mentionCandidates,
    FutureOr<void> Function(CommentComposerPayload payload)? onSubmit,
  }) async {
    final result = await showAppBottomModal<bool>(
      context: context,
      builder: (ctx) => _CommentInputSheet(
        postId: postId,
        config: config,
        replyTo: replyTo,
        surfaceMode: surfaceMode,
        sourceSurface: sourceSurface,
        mentionCandidates: mentionCandidates ?? _defaultMentions,
        loadFollowingCandidates: mentionCandidates == null,
        onSubmit: onSubmit,
      ),
    );
    return result ?? false;
  }

  static final List<CommentMention> _defaultMentions = <CommentMention>[
    CommentMention(
      subjectType: 'assistant',
      subjectId: 'assistant_xiaoqu',
      displayName: AssistantText.assistantEntryXiaoqu,
    ),
  ];
}

class _CommentInputSheet extends ConsumerStatefulWidget {
  const _CommentInputSheet({
    required this.postId,
    required this.config,
    required this.surfaceMode,
    required this.sourceSurface,
    required this.mentionCandidates,
    required this.loadFollowingCandidates,
    this.replyTo,
    this.onSubmit,
  });

  final String postId;
  final CommentConfig config;
  final CommentViewData? replyTo;
  final String surfaceMode;
  final AppUiSurface sourceSurface;
  final List<CommentMention> mentionCandidates;
  final bool loadFollowingCandidates;
  final FutureOr<void> Function(CommentComposerPayload payload)? onSubmit;

  @override
  ConsumerState<_CommentInputSheet> createState() => _CommentInputSheetState();
}

class _CommentInputSheetState extends ConsumerState<_CommentInputSheet> {
  final TextEditingController _controller = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  final List<CommentMention> _selectedMentions = <CommentMention>[];
  final List<String> _attachmentMediaIds = <String>[];

  late CommentConfig _effectiveConfig;
  late List<CommentMention> _mentionCandidates;
  bool _showEmojiPanel = false;
  bool _showMentionPanel = false;
  bool _mentionCandidatesLoading = false;
  bool _followingCandidatesLoaded = false;
  Object? _mentionCandidatesError;
  bool _isUploadingAttachment = false;
  bool _isSubmitting = false;
  bool _continuationResumeScheduled = false;
  bool _draftCleared = false;
  Timer? _draftSaveTimer;
  late final String _draftActorScope;

  @override
  void initState() {
    super.initState();
    _draftActorScope = ref.read(currentUserIdProvider).trim();
    _effectiveConfig = widget.config;
    _mentionCandidates = List<CommentMention>.of(widget.mentionCandidates);
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
      if (!mounted) return;
      final resolved = _resolveComposerConfig(
        ref.read(commentRemoteConfigProvider),
        widget.config,
      );
      setState(() => _effectiveConfig = resolved);
      _focusNode.requestFocus();
    });
  }

  /// 续写本帖/本回复目标的未发草稿（仅在用户尚未输入、且无待续接登录文本时回灌）。
  Future<void> _restoreDraft() async {
    final draft = await CommentDraftStore.load(
      widget.postId,
      actorScope: _draftActorScope,
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
        final candidate = _mentionCandidates
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
        actorScope: _draftActorScope,
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
        actorScope: _draftActorScope,
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
      return loggedIn ? FoundationText.commentClosed : FoundationText.needLogin;
    }
    final replyTo = widget.replyTo;
    if (replyTo != null) {
      return ContentText.commentReplyToTemplate.replaceFirst(
        '%s',
        replyTo.authorDisplayNameSnapshot ?? replyTo.authorId,
      );
    }
    return FoundationText.commentPlaceholder;
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
      _showMentionPanel = false;
      if (_showEmojiPanel) {
        _focusNode.unfocus();
      } else {
        _focusNode.requestFocus();
      }
    });
  }

  void _toggleMentionPanel() {
    final shouldShow = !_showMentionPanel;
    setState(() {
      _showMentionPanel = shouldShow;
      _showEmojiPanel = false;
    });
    if (!shouldShow) {
      _focusNode.requestFocus();
      return;
    }
    _focusNode.unfocus();
    if (widget.loadFollowingCandidates && !_followingCandidatesLoaded) {
      unawaited(_loadFollowingMentionCandidates());
    }
  }

  Future<void> _loadFollowingMentionCandidates() async {
    if (_mentionCandidatesLoading || _followingCandidatesLoaded) return;
    final session = ref.read(authSessionControllerProvider);
    final personaId = session.activePersonaId.trim();
    if (!session.isAuthenticated || personaId.isEmpty) {
      return;
    }
    setState(() {
      _mentionCandidatesLoading = true;
      _mentionCandidatesError = null;
    });
    try {
      final page = await ref
          .read(personaRelationshipQueryProvider(widget.sourceSurface))
          .listFollowing(personaId: personaId, limit: 20);
      if (!mounted) return;
      final merged = <String, CommentMention>{
        for (final candidate in _mentionCandidates)
          candidate.subjectId: candidate,
      };
      for (final relation in page.items) {
        final subjectId = relation.personaId.trim();
        final displayName = relation.displayName.trim();
        if (subjectId.isEmpty || displayName.isEmpty) continue;
        merged.putIfAbsent(
          subjectId,
          () => CommentMention(
            subjectType: 'user',
            subjectId: subjectId,
            displayName: displayName,
          ),
        );
      }
      setState(() {
        _mentionCandidates = merged.values.toList(growable: false);
        _mentionCandidatesLoading = false;
        _followingCandidatesLoaded = true;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _mentionCandidatesLoading = false;
        _mentionCandidatesError = error;
      });
    }
  }

  void _addMention(CommentMention candidate) {
    final displayName = candidate.displayName?.trim() ?? '';
    if (displayName.isEmpty) return;
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
    _insertText('${ContentText.commentMention}$displayName ');
    if (_showEmojiPanel || _showMentionPanel) {
      setState(() {
        _showEmojiPanel = false;
        _showMentionPanel = false;
      });
    }
    _focusNode.requestFocus();
  }

  Future<void> _addImageAttachment() async {
    if (_attachmentMediaIds.length >= _effectiveConfig.maxImageAttachments) {
      AppToast.show(
        context,
        ContentText.commentAttachmentLimitReachedTemplate.replaceFirst(
          '%s',
          '${_effectiveConfig.maxImageAttachments}',
        ),
      );
      return;
    }
    final path = await ref
        .read(imagePickGatewayProvider)
        .pickImage(
          context,
          source: ImagePickSource.photoLibrary,
          cameraRouteName: PageAccessInternalRoutes.commentMediaPickerCamera,
          galleryRouteName: PageAccessInternalRoutes.commentMediaPickerGallery,
        );
    if (!mounted || path == null || path.trim().isEmpty) return;
    setState(() => _isUploadingAttachment = true);
    try {
      final uploadService = ref.read(
        widget.surfaceMode == 'immersive_split'
            ? workBrowserContentMediaUploadServiceProvider
            : homeFeedContentMediaUploadServiceProvider,
      );
      final source = await ref
          .read(contentMediaSourceReaderProvider)
          .prepare(path);
      final uploaded = await uploadService.uploadPreparedSource(
        source: source,
        mediaType: MediaType.image,
        mimeType: contentMediaMimeTypeForPath(path, MediaType.image),
        uploadStream: ref.read(contentMediaStreamObjectUploadProvider),
      );
      if (!mounted) return;
      setState(() => _attachmentMediaIds.add(uploaded.assetId));
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
      mentions: List<CommentMention>.unmodifiable(_selectedMentions),
    );
  }

  void _submit() {
    final content = _controller.text.trim();
    if (content.isEmpty || _isSubmitting) return;
    if (content.length > _effectiveConfig.maxLength) {
      AppToast.show(context, FoundationText.commentTooLong);
      return;
    }
    if (_attachmentMediaIds.length > _effectiveConfig.maxImageAttachments) {
      AppToast.show(
        context,
        ContentText.commentAttachmentLimitReachedTemplate.replaceFirst(
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
              mentions: List<CommentMention>.unmodifiable(_selectedMentions),
            ),
          );
      unawaited(
        requireLogin(
          ref,
          context,
          AuthGateReason.comment,
          dismissFallback: AppRoutePaths.home,
          dismissPolicy: LoginDismissPolicy.safeFallback,
        ),
      );
      return;
    }

    unawaited(_performSubmit());
  }

  /// 登录态翻转为已认证时，消费本帖待续接评论并在原浮层自动续提。
  void _maybeResumeContinuation({int remainingFrames = 30}) {
    if (_isSubmitting ||
        _continuationResumeScheduled ||
        !ref.read(authSessionControllerProvider).isAuthenticated) {
      return;
    }
    _continuationResumeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _continuationResumeScheduled = false;
      if (!mounted ||
          _isSubmitting ||
          !ref.read(authSessionControllerProvider).isAuthenticated) {
        return;
      }
      if (!(ModalRoute.of(context)?.isCurrent ?? true)) {
        if (remainingFrames > 0) {
          _maybeResumeContinuation(remainingFrames: remainingFrames - 1);
          WidgetsBinding.instance.scheduleFrame();
        }
        return;
      }
      final pending = ref
          .read(authContinuationProvider.notifier)
          .take<SubmitCommentContinuation>();
      if (pending == null) return;
      // 续接帖与本浮层不一致：放回槽位，交由对应宿主续接。
      if ((pending.postId != null && pending.postId != widget.postId) ||
          pending.replyToCommentId != widget.replyTo?.id) {
        ref.read(authContinuationProvider.notifier).set(pending);
        return;
      }
      setState(() {
        _controller.text = pending.content;
        _controller.selection = TextSelection.collapsed(
          offset: _controller.text.length,
        );
        _attachmentMediaIds
          ..clear()
          ..addAll(pending.attachmentMediaIds);
        _selectedMentions
          ..clear()
          ..addAll(pending.mentions);
      });
      unawaited(_performSubmit());
    });
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
        child: SizedBox.expand(
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
                                widget.replyTo!.authorDisplayNameSnapshot ??
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
            semanticLabel: ContentText.commentAttachImage,
            onTap: _isUploadingAttachment ? null : _addImageAttachment,
          ),
          SizedBox(width: AppSpacing.md),
          _ToolIcon(
            key: TestKeys.commentMentionButton,
            icon: CupertinoIcons.at,
            isDark: isDark,
            active: _showMentionPanel,
            semanticLabel: ContentText.commentMention,
            onTap: _toggleMentionPanel,
          ),
          SizedBox(width: AppSpacing.md),
          _ToolIcon(
            icon: _showEmojiPanel
                ? CupertinoIcons.keyboard
                : CupertinoIcons.smiley,
            isDark: isDark,
            active: _showEmojiPanel,
            semanticLabel: ChatText.emojiRecent,
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
    if (_showMentionPanel) {
      return _buildMentionPicker(isDark);
    }
    if (_showEmojiPanel) {
      return UnifiedEmojiPicker(onEmojiSelected: _insertText);
    }
    return _RecentEmojiStrip(isDark: isDark, onSelected: _insertText);
  }

  Widget _buildMentionPicker(bool isDark) {
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return ConstrainedBox(
      key: TestKeys.commentMentionPicker,
      constraints: const BoxConstraints(
        maxHeight: AppSpacing.commentComposerMaxHeight,
      ),
      child: _mentionCandidatesLoading
          ? AppRequestFeedback.section()
          : _mentionCandidatesError != null
          ? Center(
              child: CupertinoButton(
                onPressed: _loadFollowingMentionCandidates,
                child: Text(ContentText.commentMentionPickerRetry),
              ),
            )
          : _mentionCandidates.isEmpty
          ? Center(
              child: Text(
                ContentText.commentMentionPickerEmpty,
                style: TextStyle(fontSize: AppTypography.sm, color: secondary),
              ),
            )
          : ListView(
              shrinkWrap: true,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.xs,
              ),
              children: <Widget>[
                Text(
                  ContentText.commentMentionPickerTitle,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.medium,
                    color: secondary,
                  ),
                ),
                ..._mentionCandidates.map(
                  (candidate) => CupertinoButton(
                    alignment: Alignment.centerLeft,
                    padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
                    onPressed: () => _addMention(candidate),
                    child: Text(candidate.displayName?.trim() ?? ''),
                  ),
                ),
              ],
            ),
    );
  }
}
