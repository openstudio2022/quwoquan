part of 'create_page.dart';

/// 创作草稿会话的持久化、恢复与脏状态判定。
///
/// 扩展只复用 [_CreatePageState] 的控制器和生命周期，不引入第二份可变状态。
extension _CreatePageStateDraftHelpers on _CreatePageState {
  String? get _activeDraftId {
    final draftId = ref.read(createEditorProvider).draftId?.trim() ?? '';
    if (draftId.isNotEmpty) {
      return draftId;
    }
    final initialDraftId = widget.initialDraftId?.trim() ?? '';
    return initialDraftId.isEmpty ? null : initialDraftId;
  }

  void _handleFocusLossFlush() {
    if (_titleFocusNode.hasFocus || _bodyFocusNode.hasFocus) {
      return;
    }
    unawaited(_flushDraftIfDirty('focus_blur'));
  }

  Future<void> _flushDraftIfDirty(String reason) async {
    await _draftSessionController.flushIfDirty(reason: reason);
  }

  String _draftContentFingerprint(CreateEditorState state) {
    return [
      state.draftFlowKind.name,
      state.editorKind.name,
      state.mediaKind.name,
      state.imagePaths.join('|'),
      state.videoPath,
      state.originalVideoPath,
      state.videoThumbnail,
      state.isOneTapMovie,
      state.oneTapMoviePath,
      state.oneTapMovieEffectId,
      state.videoDurationMs,
      state.videoTrimStartMs,
      state.videoTrimEndMs,
      state.videoCoverTimeMs,
      state.videoMuted,
      state.currentMediaIndex,
      state.title,
      state.body,
      state.articleDocument.title,
      state.articleDocument.body,
      state.articleTemplate.name,
      state.articlePaperTexture.name,
      state.articleFontPreset.name,
      state.articleCoverImagePath,
      state.titlePresentation.name,
      state.titleHintDismissed,
      state.settings.isPublic,
      state.settings.circleIds.join('|'),
      state.settings.circleNames.join('|'),
      state.settings.locationName,
      state.settings.locationPoi?.id ?? '',
      state.settings.summary,
      state.settings.tagRefs.join('|'),
      state.settings.entityRefs.join('|'),
      state.settings.assistantUsePolicy,
    ].join('::');
  }

  Future<void> _saveDraft({
    bool silent = false,
    String flushReason = 'explicit',
  }) async {
    final state = ref.read(createEditorProvider);
    if (!state.hasContent && _activeDraftId == null) {
      _draftSessionController.markIdle();
      return;
    }
    _draftSessionController.markSaving();
    final now = DateTime.now().millisecondsSinceEpoch;
    final nextId = _activeDraftId ?? state.draftId ?? 'draft_$now';
    final nextDraft = CreateDraft(
      id: nextId,
      updatedAtMs: now,
      state: state.copyWith(draftId: nextId),
    );
    try {
      ref.read(createEditorProvider.notifier).setDraftId(nextId);
      final draftStore = ref.read(createDraftStoreProvider.notifier);
      await draftStore.saveDraft(nextDraft, currentDraftId: nextId);
      await draftStore.reload();
      final verified = await draftStore.getDraft(nextId);
      if (verified == null || verified.id != nextId) {
        throw StateError('saved draft is not readable: $nextId');
      }
      _draftSessionController.markSaved();
      await reportCreateEditorSurfaceEvent(
        ref,
        flushReason == 'explicit'
            ? 'create_draft_saved'
            : 'draft_autosave_flush',
        <String, Object?>{
          ...createEditorSurfaceExtrasEditorKind(nextDraft.state.editorKind),
          'reason': flushReason,
        },
      );
      if (!silent && mounted) {
        AppToast.show(context, UITextConstants.saveDraft);
      }
    } catch (error) {
      _draftSessionController.markFailed();
      if (!silent && mounted) {
        await AppActionErrorFeedback.show(
          context,
          semantic: runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.backgroundAction,
            scope: UiErrorScope.global,
            allowRetry: false,
          ),
        );
      }
      rethrow;
    }
  }

  Future<void> _clearCurrentDraft() async {
    final currentDraftId = _activeDraftId;
    if (currentDraftId == null) {
      return;
    }
    ref.read(createEditorProvider.notifier).setDraftId(null);
    await ref
        .read(createDraftStoreProvider.notifier)
        .deleteDraft(currentDraftId);
    _draftSessionController.markIdle();
  }

  Future<void> _restoreDraft(CreateDraft draft) async {
    var effectiveDraft = draft;
    if (draft.flowKind == CreateDraftFlowKind.video &&
        draft.state.videoThumbnail.trim().isEmpty &&
        draft.state.videoPath.trim().isNotEmpty) {
      final repairedThumbnail = await _generateVideoThumbnail(
        draft.state.videoPath,
      );
      if ((repairedThumbnail?.trim().isNotEmpty ?? false) &&
          repairedThumbnail != null) {
        effectiveDraft = CreateDraft(
          id: draft.id,
          updatedAtMs: draft.updatedAtMs,
          state: draft.state.copyWith(
            draftId: draft.id,
            videoThumbnail: repairedThumbnail,
          ),
          sourceType: draft.sourceType,
        );
        await ref
            .read(createDraftStoreProvider.notifier)
            .saveDraft(effectiveDraft, currentDraftId: draft.id);
      }
    }
    ref.read(createEditorProvider.notifier).restoreFromDraft(effectiveDraft);
    _syncControllersFromState(effectiveDraft.state);
    await ref
        .read(createDraftStoreProvider.notifier)
        .setCurrentDraftId(effectiveDraft.id);
    _draftSessionController.resumeAfterRestore();
    await reportCreateEditorSurfaceEvent(
      ref,
      'draft_restore_success',
      <String, Object?>{
        ...createEditorSurfaceExtrasEditorKind(effectiveDraft.state.editorKind),
        'flowKind': effectiveDraft.flowKind.name,
      },
    );
    if (effectiveDraft.state.editorKind == CreateEditorKind.text) {
      _focusBodyField();
    }
  }
}
