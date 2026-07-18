part of 'create_page.dart';

extension _CreatePageStateMediaHelpers on _CreatePageState {
  Future<void> _publish() async {
    // 防御性二次拦截：发布是需登录写动作。创作页已被路由守卫保护，这里再兜底一次。
    if (!await requireLogin(ref, context, AuthGateReason.createPost)) {
      return;
    }
    if (!mounted) return;
    var state = ref.read(createEditorProvider);
    if (_isPublishing) {
      return;
    }
    if (!_canPublish(state)) {
      AppToast.show(context, '先写点内容');
      return;
    }
    if (_useImmersiveArticleExperience(state)) {
      await _flushDraftIfDirty('subpage_push');
      if (!mounted) {
        return;
      }
      final proceed = await Navigator.of(context).push<bool>(
        CupertinoPageRoute<bool>(
          settings: const RouteSettings(
            name: PageAccessInternalRoutes.createPageArticleTypography,
          ),
          fullscreenDialog: true,
          builder: (_) => const ArticleTypographyPage(),
        ),
      );
      if (proceed != true) {
        return;
      }
      state = ref.read(createEditorProvider);
    }
    final confirmedSettings = await _showPublishConfirmationSheet(state);
    if (confirmedSettings == null) {
      return;
    }
    final publishState = state.copyWith(settings: confirmedSettings);
    ref.read(createEditorProvider.notifier).setSettings(confirmedSettings);
    _setMountedState(() => _isPublishing = true);
    try {
      await _saveDraft(silent: true, flushReason: 'pre_publish');
      final localDraftId = _activeDraftId;
      if (localDraftId == null) {
        throw StateError('local draft id unavailable');
      }
      final media = ref.read(createContentMediaFacetProvider);
      final preparedPayload = await buildPostPublicationPayloadWithRemoteMedia(
        media: media,
        fileStorageGateway: ref.read(fileStorageGatewayProvider),
        state: publishState,
        uploadObject: ref.read(contentMediaObjectUploadProvider),
      );
      final command = await attachActivePersonaToPostPublicationCommand(
        ref,
        preparedPayload,
        localDraftId: localDraftId,
      );
      final activePersona = await ref.read(activePersonaContextProvider.future);
      final receipt = await ref
          .read(postPublicationIntentQueueProvider.notifier)
          .submit(
            command: command,
            authorPersonaId: activePersona.subAccountId,
            circleIds: confirmedSettings.isPublic
                ? confirmedSettings.circleIds
                : const <String>[],
          );
      final postId = receipt.postId;
      if (postId.isEmpty) {
        throw StateError('missing post id');
      }
      await reportCreateEditorSurfaceEvent(
        ref,
        'create_publish_success',
        createEditorSurfaceExtrasPublishSuccess(preparedPayload.payload),
      );
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.publishAction);
      _doClose();
    } on PostPublicationQueuedException {
      await reportCreateEditorSurfaceEvent(ref, 'create_publish_queued');
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.publishQueued);
      _doClose();
    } catch (error) {
      await reportCreateEditorSurfaceEvent(ref, 'create_publish_failure');
      if (mounted) {
        final semantic = '$error'.contains('active persona context')
            ? UiErrorSemantic(
                category: UiErrorCategory.submit,
                scope: UiErrorScope.global,
                title: '发布未完成',
                message: '当前分身上下文还没准备好，稍后可以再试一次。',
                primaryAction: const UiErrorAction(
                  type: UiErrorActionType.retry,
                  label: UITextConstants.tryAgain,
                ),
                dismissible: true,
              )
            : runtimeErrorSemantic(
                context,
                error: error,
                category: UiErrorCategory.submit,
                scope: UiErrorScope.global,
              );
        await AppActionErrorFeedback.show(
          context,
          semantic: semantic,
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _publish();
            }
          },
        );
      }
    } finally {
      if (mounted) {
        _setMountedState(() => _isPublishing = false);
      }
    }
  }

  Widget _buildTextEditor(CreateEditorState state) {
    return ArticleEditor(
      state: state,
      titleController: _titleController,
      titleFocusNode: _titleFocusNode,
      onTitleChanged: (value) {
        ref.read(createEditorProvider.notifier).updateTitle(value);
      },
      onTitleStyleChanged: (style) {
        ref.read(createEditorProvider.notifier).updateArticleTitleStyle(style);
      },
      onUpdateNodeText: (nodeId, value) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticleNodeText(nodeId, value);
      },
      onUpdateWrapParagraphTexts: (figureNodeId, narrowText, belowText) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticleWrapParagraphTexts(
              figureNodeId,
              narrowText: narrowText,
              belowText: belowText,
            );
      },
      onUpdateNodeImageLayout: (nodeId, layout) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticleNodeImageLayout(nodeId, layout);
      },
      onUpdateNodeCaption: (nodeId, caption) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticleNodeCaption(nodeId, caption);
      },
      onEditNodeImage: (nodeId) async {
        final path = ref
            .read(createEditorProvider.notifier)
            .articleNodeImageUrl(nodeId);
        if (path == null || path.trim().isEmpty || !mounted) return;
        await _flushDraftIfDirty('subpage_push');
        if (!mounted) return;
        final result = await Navigator.of(context).push<String?>(
          MaterialPageRoute<String?>(
            settings: const RouteSettings(
              name: PageAccessInternalRoutes.createPageImagePreview,
            ),
            fullscreenDialog: true,
            builder: (_) => ImageEditorPage(
              initialPath: path,
              source: 'create',
              index: 0,
              total: 1,
              imagePaths: <String>[path],
            ),
          ),
        );
        if (!mounted || result == null || result.trim().isEmpty) return;
        ref
            .read(createEditorProvider.notifier)
            .replaceArticleNodeImage(nodeId, result.trim());
      },
      onRemoveNodeImage: (nodeId) {
        ref.read(createEditorProvider.notifier).removeArticleNode(nodeId);
      },
      onInsertImageAfter: (afterNodeId) async {
        await _pickImagesForArticleNode(afterNodeId);
      },
      onInsertImageAtSelection: (nodeId, selectionOffset) async {
        await _pickImagesForArticleTextSelection(nodeId, selectionOffset);
      },
      onActiveBlockChanged: (blockId) {
        ref.read(createEditorProvider.notifier).setActiveArticleBlock(blockId);
      },
      onInsertTextNodeAfter: (afterNodeId, {String initialText = ''}) {
        return ref
            .read(createEditorProvider.notifier)
            .insertTextNodeAfter(afterNodeId, initialText: initialText);
      },
      onEnsureWrapNodeGroup: (figureNodeId, {int? splitOffset}) {
        return ref
            .read(createEditorProvider.notifier)
            .ensureArticleWrapNodeGroup(figureNodeId, splitOffset: splitOffset);
      },
      onArticleIntrinsicImageResolved: () {
        if (mounted) _setMountedState(() {});
      },
      onPaperTextureSelected: (texture) {
        ref.read(createEditorProvider.notifier).setArticlePaperTexture(texture);
      },
      onFontSelected: (preset) {
        ref.read(createEditorProvider.notifier).setArticleFontPreset(preset);
      },
      immersive: widget.initialAction == EditorStartAction.write,
      onUndo: () => ref.read(createEditorProvider.notifier).undoArticle(),
      onRedo: () => ref.read(createEditorProvider.notifier).redoArticle(),
      canUndo: ref.read(createEditorProvider.notifier).canUndoArticle,
      canRedo: ref.read(createEditorProvider.notifier).canRedoArticle,
      onUpdateNodeType: (nodeId, type) {
        ref
            .read(createEditorProvider.notifier)
            .updateArticleNodeType(nodeId, type);
      },
      onToggleInlineStyle:
          (
            nodeId,
            start,
            end, {
            bool? bold,
            bool? italic,
            bool? underline,
            bool? strikethrough,
          }) {
            ref
                .read(createEditorProvider.notifier)
                .toggleArticleInlineStyle(
                  nodeId,
                  start,
                  end,
                  bold: bold,
                  italic: italic,
                  underline: underline,
                  strikethrough: strikethrough,
                );
          },
      onInsertEntityMention: _insertEntityMentionFromSelection,
      onCommitTextEdit: () {
        ref.read(createEditorProvider.notifier).commitArticleTextEdit();
      },
    );
  }

  Widget _buildMediaStrip({
    required CreateEditorState state,
    required Future<void> Function() onAdd,
    required Future<void> Function(int index) onTapImage,
    required void Function(int index) onRemove,
  }) {
    final isVideo =
        state.mediaKind == CreateMediaKind.video && state.videoPath.isNotEmpty;
    final items = isVideo
        ? <String>[
            state.videoThumbnail.trim().isEmpty
                ? state.videoPath
                : state.videoThumbnail,
          ]
        : state.imagePaths;
    return LayoutBuilder(
      builder: (context, constraints) {
        final spacing = AppSpacing.intraGroupSm;
        final columns = _mediaColumnsForWidth(constraints.maxWidth);
        final tileWidth =
            ((constraints.maxWidth - spacing * (columns - 1)) / columns)
                .clamp(72.0, 148.0)
                .toDouble();
        final tileHeight = tileWidth * _mediaTileAspectRatioForColumns(columns);
        final addEnabled = state.editorKind == CreateEditorKind.text
            ? true
            : _canAddMoreImages(state);
        final addLabel = state.editorKind == CreateEditorKind.text
            ? '添加图片'
            : (items.isEmpty ? '添加' : '添加图片');
        if (isVideo) {
          final videoWidth = math
              .min(tileWidth * 1.2, constraints.maxWidth)
              .toDouble();
          return Column(
            children: <Widget>[
              Align(
                alignment: Alignment.center,
                child: _buildMediaTile(
                  assetPath: items.first,
                  index: 0,
                  isVideo: true,
                  width: videoWidth,
                  height: tileHeight,
                  isEmphasized: true,
                  onTap: _editCurrentVideo,
                  onRemove: () => onRemove(0),
                ),
              ),
              SizedBox(height: spacing),
              Text(
                UITextConstants.createVideoEditFeaturesHint,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onAdd,
                child: const Text(UITextConstants.createReplaceVideoLabel),
              ),
            ],
          );
        }
        if (items.isEmpty) {
          return Align(
            alignment: Alignment.centerLeft,
            child: _AddThumbnailButton(
              key: TestKeys.createMediaAddButton,
              onPressed: onAdd,
              width: tileWidth,
              height: tileHeight,
              label: addLabel,
              enabled: addEnabled,
            ),
          );
        }

        // 统一拖拽重排：长按起拖 + 兄弟实时让位 + 松手提交，几何与三场景共用
        // MediaReorderableView（替换旧的「松手按重叠面积」一次性落点方案）。
        // 网格竖向边缘自动滚动仍复用页面既有 _autoScrollDuringMediaDrag。
        return MediaReorderableView(
          itemCount: items.length,
          layout: MediaReorderableLayout.grid,
          crossAxisCount: columns,
          spacing: spacing,
          runSpacing: spacing,
          itemSize: Size(tileWidth, tileHeight),
          onReorder: (oldIndex, newIndex) => ref
              .read(createEditorProvider.notifier)
              .reorderImages(oldIndex, newIndex),
          onDragGlobalPositionChanged: _autoScrollDuringMediaDrag,
          trailing: _AddThumbnailButton(
            key: TestKeys.createMediaAddButton,
            onPressed: onAdd,
            width: tileWidth,
            height: tileHeight,
            label: addLabel,
            enabled: addEnabled,
          ),
          itemBuilder: (context, index, isDragging) => _buildMediaTile(
            assetPath: items[index],
            index: index,
            isVideo: false,
            width: tileWidth,
            height: tileHeight,
            isEmphasized: isDragging,
            isPressed: _pressedMediaPath == items[index],
            onTap: () => onTapImage(index),
            onRemove: () => onRemove(index),
          ),
        );
      },
    );
  }

  Widget _buildMediaTile({
    required String assetPath,
    required int index,
    required bool isVideo,
    required double width,
    required double height,
    required Future<void> Function() onTap,
    required VoidCallback onRemove,
    bool isEmphasized = false,
    bool isPressed = false,
    bool showRemoveButton = true,
    bool showFloatingShadow = false,
  }) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final mediaScrim = AppColorsFunctional.getColor(
      isDark,
      ColorType.createMediaOverlayBase,
    );
    final onLightContent = AppColorsFunctional.getColor(
      isDark,
      ColorType.badgeForeground,
    );
    final glassBorder = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundInverse,
    );
    final deleteGlassTint = isDark
        ? AppColors.black.withValues(alpha: 0.24)
        : AppColors.iosSecondaryFill(context).withValues(alpha: 0.82);
    final deleteIconColor = AppColors.iosLabel(context);
    final deleteRingColor = AppColors.iosSeparator(
      context,
    ).withValues(alpha: 0.2);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) {
        if (!mounted) {
          return;
        }
        _setMountedState(() {
          _pressedMediaPath = assetPath;
        });
      },
      onTapCancel: () {
        if (!mounted) {
          return;
        }
        _setMountedState(() {
          if (_pressedMediaPath == assetPath) {
            _pressedMediaPath = null;
          }
        });
      },
      onTap: () async {
        if (mounted) {
          _setMountedState(() {
            if (_pressedMediaPath == assetPath) {
              _pressedMediaPath = null;
            }
          });
        }
        await onTap();
      },
      child: SizedBox(
        key: ValueKey<String>('create-media-tile-$assetPath'),
        width: width,
        height: height,
        child: Transform.scale(
          scale: isEmphasized ? 1.015 : 1.0,
          child: Stack(
            children: <Widget>[
              AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                curve: Curves.easeOutCubic,
                width: width,
                height: height,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppSpacing.containerSm),
                  border: Border.all(
                    color: isEmphasized
                        ? AppColors.iosAccentLight
                        : CupertinoColors.separator
                              .resolveFrom(context)
                              .withValues(alpha: 0.12),
                    width: isEmphasized
                        ? AppSpacing.oneHalf
                        : AppSpacing.hairline,
                  ),
                  boxShadow: isEmphasized
                      ? <BoxShadow>[
                          BoxShadow(
                            color: AppColors.iosAccentLight.withValues(
                              alpha: showFloatingShadow ? 0.28 : 0.14,
                            ),
                            blurRadius: showFloatingShadow
                                ? AppSpacing.twenty
                                : AppSpacing.ten,
                            offset: Offset(
                              0,
                              showFloatingShadow
                                  ? AppSpacing.ten
                                  : AppSpacing.contentSpacingXs,
                            ),
                            spreadRadius: showFloatingShadow
                                ? AppSpacing.oneHalf
                                : 0,
                          ),
                        ]
                      : const <BoxShadow>[],
                ),
                clipBehavior: Clip.antiAlias,
                child: Stack(
                  fit: StackFit.expand,
                  children: <Widget>[
                    if (isVideo)
                      Stack(
                        fit: StackFit.expand,
                        children: <Widget>[
                          Image.file(
                            File(assetPath),
                            fit: BoxFit.cover,
                            errorBuilder: (context, error, stackTrace) =>
                                Container(
                                  decoration: const BoxDecoration(
                                    gradient: LinearGradient(
                                      begin: Alignment.topCenter,
                                      end: Alignment.bottomCenter,
                                      colors: <Color>[
                                        AppColors
                                            .createMediaFallbackGradientTop,
                                        AppColors
                                            .createMediaFallbackGradientBottom,
                                      ],
                                    ),
                                  ),
                                ),
                          ),
                          DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: <Color>[
                                  mediaScrim.withValues(
                                    alpha: isDark ? 0.14 : 0.08,
                                  ),
                                  mediaScrim.withValues(
                                    alpha: isDark ? 0.38 : 0.34,
                                  ),
                                ],
                              ),
                            ),
                          ),
                          Center(
                            child: Container(
                              width: AppSpacing.buttonHeight,
                              height: AppSpacing.buttonHeight,
                              decoration: BoxDecoration(
                                color: mediaScrim.withValues(
                                  alpha: isDark ? 0.22 : 0.28,
                                ),
                                shape: BoxShape.circle,
                                border: Border.all(
                                  color: glassBorder.withValues(
                                    alpha: isDark ? 0.2 : 0.14,
                                  ),
                                  width: AppSpacing.hairline,
                                ),
                              ),
                              child: Icon(
                                CupertinoIcons.play_fill,
                                color: onLightContent.withValues(alpha: 0.96),
                                size: AppSpacing.iconLarge,
                              ),
                            ),
                          ),
                        ],
                      )
                    else
                      Image.file(
                        File(assetPath),
                        fit: BoxFit.cover,
                        errorBuilder: (context, error, stackTrace) => Container(
                          color: mediaScrim.withValues(
                            alpha: isDark ? 0.16 : 0.12,
                          ),
                        ),
                      ),
                    if (isVideo)
                      Positioned(
                        left: AppSpacing.intraGroupXs,
                        bottom: AppSpacing.intraGroupXs,
                        child: _PreviewBadge(
                          label: UITextConstants.createVideoBadgeEditLabel,
                          backgroundColor: mediaScrim.withValues(
                            alpha: isDark ? 0.42 : 0.48,
                          ),
                        ),
                      ),
                    if (isVideo)
                      Positioned(
                        left: AppSpacing.intraGroupXs,
                        top: AppSpacing.intraGroupXs,
                        child: _PreviewBadge(
                          label: UITextConstants.createVideoKindBadgeLabel,
                          backgroundColor: mediaScrim.withValues(
                            alpha: isDark ? 0.42 : 0.48,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              if (showRemoveButton)
                Positioned(
                  right: AppSpacing.intraGroupXs,
                  top: AppSpacing.intraGroupXs,
                  child: GestureDetector(
                    key: index == 0 ? TestKeys.createMediaRemoveButton : null,
                    onTap: onRemove,
                    child: ClipOval(
                      child: BackdropFilter(
                        filter: ImageFilter.blur(
                          sigmaX: AppSpacing.containerSm,
                          sigmaY: AppSpacing.containerSm,
                        ),
                        child: Container(
                          width:
                              AppSpacing.iconMedium + AppSpacing.intraGroupSm,
                          height:
                              AppSpacing.iconMedium + AppSpacing.intraGroupSm,
                          decoration: BoxDecoration(
                            color: deleteGlassTint,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: deleteRingColor,
                              width: AppSpacing.hairline,
                            ),
                          ),
                          child: Icon(
                            CupertinoIcons.xmark,
                            size: AppTypography.xsPlus,
                            color: deleteIconColor,
                          ),
                        ),
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
}
