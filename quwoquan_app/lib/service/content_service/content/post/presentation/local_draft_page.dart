import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart'
    show fileStorageGatewayProvider;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_provider_bridge.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/post_publication_task_section.dart';

class LocalDraftPage extends ConsumerStatefulWidget {
  const LocalDraftPage({super.key});

  @override
  ConsumerState<LocalDraftPage> createState() => _LocalDraftPageState();
}

class _LocalDraftPageState extends ConsumerState<LocalDraftPage>
    with WidgetsBindingObserver {
  bool _didReportOpen = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      unawaited(ref.read(createDraftStoreProvider.notifier).reload());
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(ref.read(createDraftStoreProvider.notifier).reload());
    }
  }

  @override
  Widget build(BuildContext context) {
    final draftsAsync = ref.watch(createDraftStoreProvider);
    final publicationIntents = ref.watch(
      postPublicationIntentQueueProvider.select((state) => state.intents),
    );
    final pageBackground = AppColors.iosPageBackground(context);
    return AppScaffold(
      key: TestKeys.localDraftPage,
      backgroundColor: pageBackground,
      navigationBar: AppNavigationBar(
        middle: Text(
          CreationText.localDraftsTitle,
          style: TextStyle(
            color: AppColors.iosLabel(context),
            fontSize: AppTypography.iosNavTitle,
            fontWeight: AppTypography.semiBold,
          ),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).maybePop(),
        ),
      ),
      child: SafeArea(
        top: false,
        bottom: false,
        child: draftsAsync.when(
          data: (snapshot) =>
              _buildLoadedState(context, snapshot, publicationIntents),
          loading: () => AppRequestFeedback.section(),
          error: (error, _) => AppSectionErrorState(
            semantic: ensureRetryUiErrorSemantic(
              runtimeErrorSemantic(
                context,
                error: error,
                category: UiErrorCategory.sectionLoad,
                scope: UiErrorScope.section,
              ),
            ),
            onAction: (_) =>
                ref.read(createDraftStoreProvider.notifier).reload(),
          ),
        ),
      ),
    );
  }

  Widget _buildLoadedState(
    BuildContext context,
    CreateDraftStoreState snapshot,
    List<LocalPostPublicationIntent> publicationIntents,
  ) {
    final drafts = snapshot.drafts;
    if (!_didReportOpen) {
      _didReportOpen = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        unawaited(
          reportCreateEditorSurfaceEvent(
            ref,
            'draft_list_open',
            <String, Object?>{'draftCount': drafts.length},
            AppUiSurfaces.localDrafts.id,
          ),
        );
      });
    }
    return CustomScrollView(
      slivers: [
        if (publicationIntents.isNotEmpty)
          SliverToBoxAdapter(
            child: PostPublicationTaskSection(
              intents: publicationIntents,
              onRetry: (intent) => unawaited(
                ref
                    .read(postPublicationIntentQueueProvider.notifier)
                    .retryPending(intent.command.localDraftId),
              ),
              onEdit: (intent) => context.push(
                AppRoutePaths.create(draftId: intent.command.localDraftId),
              ),
              onRemove: (intent) => unawaited(
                ref
                    .read(postPublicationIntentQueueProvider.notifier)
                    .cancelPending(intent.command.localDraftId),
              ),
            ),
          ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerSm,
              AppSpacing.containerMd,
              0,
            ),
            child: _LocalDraftNoticeBanner(
              text: CreationText.localDraftsDeviceOnlyNotice,
            ),
          ),
        ),
        if (drafts.isEmpty)
          const SliverFillRemaining(
            hasScrollBody: false,
            child: AppEmptyState(
              key: TestKeys.localDraftEmptyState,
              icon: CupertinoIcons.doc_plaintext,
              title: MediaText.noDraft,
              subtitle: CreationText.localDraftEmptySubtitle,
            ),
          )
        else
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerMd,
              AppSpacing.containerMd,
              AppSpacing.xl,
            ),
            sliver: SliverMasonryGrid.count(
              crossAxisCount: 2,
              mainAxisSpacing: AppSpacing.containerMd,
              crossAxisSpacing: AppSpacing.containerMd,
              childCount: drafts.length,
              itemBuilder: (context, index) {
                final draft = drafts[index];
                return _LocalDraftCard(
                  key: ValueKey<String>('local_draft_card_${draft.id}'),
                  draft: draft,
                  mediaStateFuture: _resolveMediaState(draft),
                  onOpen: () => unawaited(_openDraft(draft)),
                  onDelete: () => _confirmDeleteDraft(draft),
                );
              },
            ),
          ),
      ],
    );
  }

  Future<_DraftMediaState> _resolveMediaState(CreateDraft draft) async {
    final gateway = ref.read(fileStorageGatewayProvider);
    final flowKind = draft.flowKind;
    final articleCover = draft.state.articleCoverImagePath.trim();
    final firstImage = draft.state.imagePaths.isEmpty
        ? ''
        : draft.state.imagePaths.first.trim();
    final videoThumbnail = draft.state.videoThumbnail.trim();
    final videoPath = draft.state.videoPath.trim();
    final previewSource = switch (flowKind) {
      CreateDraftFlowKind.article =>
        articleCover.isNotEmpty ? articleCover : firstImage,
      CreateDraftFlowKind.image => firstImage,
      CreateDraftFlowKind.video => videoThumbnail,
    };
    final hasVideoFile =
        videoPath.isNotEmpty &&
        (isRemoteMediaImageSource(videoPath) ||
            !gateway.isSupported ||
            await gateway.exists(localMediaImagePath(videoPath)));
    final resolvedPreview = previewSource.trim();
    if (resolvedPreview.isEmpty) {
      return _DraftMediaState(
        imageSource: null,
        missingVisual: flowKind != CreateDraftFlowKind.article,
        hasRecoverablePrimaryAsset: flowKind == CreateDraftFlowKind.video
            ? hasVideoFile
            : false,
      );
    }
    if (isRemoteMediaImageSource(resolvedPreview) || !gateway.isSupported) {
      return _DraftMediaState(
        imageSource: resolvedPreview,
        missingVisual: false,
        hasRecoverablePrimaryAsset: flowKind == CreateDraftFlowKind.video
            ? hasVideoFile
            : true,
      );
    }
    final exists = await gateway.exists(localMediaImagePath(resolvedPreview));
    if (exists) {
      return _DraftMediaState(
        imageSource: resolvedPreview,
        missingVisual: false,
        hasRecoverablePrimaryAsset: flowKind == CreateDraftFlowKind.video
            ? hasVideoFile
            : true,
      );
    }
    return _DraftMediaState(
      imageSource: null,
      missingVisual: flowKind != CreateDraftFlowKind.article,
      hasRecoverablePrimaryAsset: flowKind == CreateDraftFlowKind.video
          ? hasVideoFile
          : false,
    );
  }

  Future<void> _confirmDeleteDraft(CreateDraft draft) async {
    await reportCreateEditorSurfaceEvent(
      ref,
      'draft_delete_click',
      <String, Object?>{'flowKind': draft.flowKind.name, 'draftId': draft.id},
      AppUiSurfaces.localDrafts.id,
    );
    if (!mounted) {
      return;
    }
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: const Text(CreationText.localDraftDeleteConfirmTitle),
          content: const Padding(
            padding: EdgeInsets.only(top: AppSpacing.sm),
            child: Text(CreationText.localDraftDeleteConfirmDesc),
          ),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text(FoundationText.cancel),
            ),
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text(CreationText.localDraftDeleteAction),
            ),
          ],
        );
      },
    );
    if (confirmed != true || !mounted) {
      return;
    }
    await reportCreateEditorSurfaceEvent(
      ref,
      'draft_delete_success',
      <String, Object?>{'flowKind': draft.flowKind.name, 'draftId': draft.id},
      AppUiSurfaces.localDrafts.id,
    );
    await ref.read(createDraftStoreProvider.notifier).deleteDraft(draft.id);
  }

  Future<void> _openDraft(CreateDraft draft) async {
    final mediaState = await _resolveMediaState(draft);
    if (!mounted) {
      return;
    }
    final blocksRestore =
        draft.flowKind == CreateDraftFlowKind.video &&
        mediaState.imageSource == null &&
        !mediaState.hasRecoverablePrimaryAsset;
    if (blocksRestore) {
      await reportCreateEditorSurfaceEvent(
        ref,
        'draft_restore_failed',
        <String, Object?>{'flowKind': draft.flowKind.name, 'draftId': draft.id},
        AppUiSurfaces.localDrafts.id,
      );
      if (!mounted) {
        return;
      }
      final confirmedDelete = await showAppCupertinoDialog<bool>(
        context: context,
        builder: (dialogContext) {
          return CupertinoAlertDialog(
            title: const Text(CreationText.localDraftUnavailableTitle),
            content: Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(CreationText.localDraftMissingVideoDesc),
            ),
            actions: [
              CupertinoDialogAction(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: const Text(FoundationText.cancel),
              ),
              CupertinoDialogAction(
                isDestructiveAction: true,
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: const Text(CreationText.localDraftDeleteAction),
              ),
            ],
          );
        },
      );
      if (confirmedDelete == true) {
        await ref.read(createDraftStoreProvider.notifier).deleteDraft(draft.id);
      }
      return;
    }
    await reportCreateEditorSurfaceEvent(
      ref,
      'draft_card_open',
      <String, Object?>{'flowKind': draft.flowKind.name, 'draftId': draft.id},
      AppUiSurfaces.localDrafts.id,
    );
    if (!mounted) {
      return;
    }
    final location = AppRoutePaths.create(draftId: draft.id);
    context.push(location);
  }
}

class _LocalDraftNoticeBanner extends StatelessWidget {
  const _LocalDraftNoticeBanner({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.warning.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: AppColors.warning.withValues(alpha: 0.22)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerSm,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              CupertinoIcons.info_circle_fill,
              size: AppSpacing.iconMedium,
              color: AppColors.warning,
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                text,
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.body,
                  fontWeight: AppTypography.medium,
                  height: AppTypography.bodyLineHeight,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LocalDraftCard extends StatelessWidget {
  const _LocalDraftCard({
    super.key,
    required this.draft,
    required this.mediaStateFuture,
    required this.onOpen,
    required this.onDelete,
  });

  final CreateDraft draft;
  final Future<_DraftMediaState> mediaStateFuture;
  final VoidCallback onOpen;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final surfaceColor = AppColors.iosGroupedSurfaceElevated(context);
    final borderColor = AppColors.iosSeparator(context).withValues(alpha: 0.35);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onOpen,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surfaceColor,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(color: borderColor),
          boxShadow: [
            BoxShadow(
              color: CupertinoColors.black.withValues(alpha: 0.04),
              blurRadius: 18,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              FutureBuilder<_DraftMediaState>(
                future: mediaStateFuture,
                builder: (context, snapshot) {
                  final mediaState = snapshot.data ?? const _DraftMediaState();
                  return _LocalDraftCardVisual(
                    draft: draft,
                    mediaState: mediaState,
                  );
                },
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  AppSpacing.containerMd,
                  AppSpacing.containerMd,
                  AppSpacing.containerSm,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _LocalDraftTypePill(label: _draftTypeLabel(draft.flowKind)),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      _draftTitle(draft),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: AppColors.iosLabel(context),
                        fontSize: AppTypography.body,
                        fontWeight: AppTypography.semiBold,
                        height: AppTypography.lineHeightCompact,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      _draftSummary(draft),
                      maxLines: 4,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: AppColors.iosSecondaryLabel(context),
                        fontSize: AppTypography.caption,
                        height: AppTypography.lineHeightRelaxed,
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  0,
                  AppSpacing.containerSm,
                  AppSpacing.containerSm,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        _formatDraftTime(context, draft.updatedAtMs),
                        style: TextStyle(
                          color: AppColors.iosSecondaryLabel(context),
                          fontSize: AppTypography.iosFootnote,
                        ),
                      ),
                    ),
                    CupertinoButton(
                      key: ValueKey<String>('local_draft_delete_${draft.id}'),
                      padding: EdgeInsets.zero,
                      minimumSize: const Size(
                        AppSpacing.iconButtonMinSizeSm,
                        AppSpacing.iconButtonMinSizeSm,
                      ),
                      onPressed: onDelete,
                      child: Icon(
                        CupertinoIcons.delete_simple,
                        size: AppSpacing.iconMedium,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LocalDraftCardVisual extends StatelessWidget {
  const _LocalDraftCardVisual({required this.draft, required this.mediaState});

  final CreateDraft draft;
  final _DraftMediaState mediaState;

  @override
  Widget build(BuildContext context) {
    final isArticle = draft.flowKind == CreateDraftFlowKind.article;
    if (mediaState.imageSource == null &&
        !mediaState.missingVisual &&
        isArticle) {
      return const SizedBox.shrink();
    }
    final placeholderText = switch (draft.flowKind) {
      CreateDraftFlowKind.image => CreationText.localDraftMissingImage,
      CreateDraftFlowKind.video => CreationText.localDraftMissingVideo,
      CreateDraftFlowKind.article => '',
    };
    final placeholder = _LocalDraftMissingMediaPlaceholder(
      isVideo: draft.flowKind == CreateDraftFlowKind.video,
      label: placeholderText,
      subtitle: mediaState.hasRecoverablePrimaryAsset
          ? CreationText.createDraftPickerPreviewFallback
          : _draftTitle(draft),
    );
    return AspectRatio(
      aspectRatio: draft.flowKind == CreateDraftFlowKind.article ? 4 / 3 : 1,
      child: mediaState.imageSource == null
          ? placeholder
          : Stack(
              fit: StackFit.expand,
              children: [
                AppMediaImage(
                  imageSource: mediaState.imageSource!,
                  fit: BoxFit.cover,
                  placeholder: placeholder,
                  errorWidget: placeholder,
                ),
                if (draft.flowKind == CreateDraftFlowKind.video)
                  Center(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: CupertinoColors.black.withValues(alpha: 0.28),
                        shape: BoxShape.circle,
                      ),
                      child: const Padding(
                        padding: EdgeInsets.all(AppSpacing.containerSm),
                        child: Icon(
                          CupertinoIcons.play_fill,
                          color: CupertinoColors.white,
                          size: AppSpacing.iconMedium,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
    );
  }
}

class _LocalDraftMissingMediaPlaceholder extends StatelessWidget {
  const _LocalDraftMissingMediaPlaceholder({
    required this.isVideo,
    required this.label,
    required this.subtitle,
  });

  final bool isVideo;
  final String label;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.iosSecondaryFill(context),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              isVideo ? CupertinoIcons.video_camera : CupertinoIcons.photo,
              size: AppSpacing.iconLarge,
              color: AppColors.iosTertiaryLabel(context),
            ),
            if (label.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                label,
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.body,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ],
            const SizedBox(height: AppSpacing.xs),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.caption,
                height: AppTypography.bodyLineHeight,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LocalDraftTypePill extends StatelessWidget {
  const _LocalDraftTypePill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.xs,
        ),
        child: Text(
          label,
          style: TextStyle(
            color: AppColors.iosSecondaryLabel(context),
            fontSize: AppTypography.iosFootnote,
            fontWeight: AppTypography.medium,
          ),
        ),
      ),
    );
  }
}

class _DraftMediaState {
  const _DraftMediaState({
    this.imageSource,
    this.missingVisual = false,
    this.hasRecoverablePrimaryAsset = false,
  });

  final String? imageSource;
  final bool missingVisual;
  final bool hasRecoverablePrimaryAsset;
}

String _draftTypeLabel(CreateDraftFlowKind flowKind) {
  return switch (flowKind) {
    CreateDraftFlowKind.image => MediaText.draftPhoto,
    CreateDraftFlowKind.video => MediaText.draftVideo,
    CreateDraftFlowKind.article => MediaText.draftArticle,
  };
}

String _draftTitle(CreateDraft draft) {
  final title = draft.state.title.trim();
  if (title.isNotEmpty) {
    return title;
  }
  return _draftTypeLabel(draft.flowKind);
}

String _draftSummary(CreateDraft draft) {
  final summary = draft.previewText.trim();
  if (summary.isNotEmpty) {
    return summary;
  }
  return CreationText.createDraftPickerPreviewFallback;
}

String _formatDraftTime(BuildContext context, int updatedAtMs) {
  final dt = DateTime.fromMillisecondsSinceEpoch(updatedAtMs);
  final localeTag = Localizations.localeOf(context).toLanguageTag();
  return DateFormat('MM-dd HH:mm', localeTag).format(dt);
}
