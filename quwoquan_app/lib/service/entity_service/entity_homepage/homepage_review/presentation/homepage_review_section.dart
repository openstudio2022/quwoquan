import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_review/application/public/homepage_review_operation_ports.dart';
import 'package:quwoquan_app/runtime/errors/generated/entity/entity_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/design_system/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_ref_label.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show homepageReviewCommandWriterProvider, homepageReviewQueryProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_review/presentation/homepage_review_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CreateHomepageReviewCommand,
        DeleteHomepageReviewCommand,
        HomepageReviewListQuery,
        HomepageReviewStatus,
        HomepageReviewView,
        MyHomepageReviewQuery,
        UpdateHomepageReviewCommand;

/// 实体主页评价区（opinion tab 主体）：
/// 写评价入口 + 我的评价（编辑/删除）+ 评价 keyset 列表。
/// 数据源：HomepageReviewQuery / HomepageReviewCommandWriter typed facet。
final class HomepageReviewSection extends ConsumerStatefulWidget {
  const HomepageReviewSection({
    super.key,
    required this.homepageId,
    this.tagOptions = const <String>[],
    this.onReviewsChanged,
    this.requireAuth,
    this.resumeComposerToken = 0,
  });

  final String homepageId;

  /// 写评价 sheet 的亮点标签候选（主页 tagRefs / categoryTags）。
  final List<String> tagOptions;

  /// 写/改/删成功后回调（宿主刷新评分摘要卡）。
  final VoidCallback? onReviewsChanged;

  /// 写操作前的登录闸口；返回 false 中止（游客场景）。
  final Future<bool> Function()? requireAuth;

  /// 登录成功后续接评价编辑器的一次性变化令牌。
  final int resumeComposerToken;

  @override
  ConsumerState<HomepageReviewSection> createState() =>
      _HomepageReviewSectionState();
}

final class _HomepageReviewSectionState
    extends ConsumerState<HomepageReviewSection> {
  bool _loading = true;
  bool _submitting = false;
  UiErrorSemantic? _errorSemantic;
  List<HomepageReviewView> _reviews = const <HomepageReviewView>[];
  String? _nextCursor;
  HomepageReviewView? _mine;
  bool _continuationResumeScheduled = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
    if (widget.resumeComposerToken > 0) {
      _scheduleReviewContinuationResume();
    }
  }

  @override
  void didUpdateWidget(covariant HomepageReviewSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.resumeComposerToken != widget.resumeComposerToken) {
      _scheduleReviewContinuationResume();
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _errorSemantic = null;
    });
    try {
      final query = ref.read(homepageReviewQueryProvider);
      final page = await query.listByHomepage(
        HomepageReviewListQuery(homepageId: widget.homepageId),
      );
      HomepageReviewView? mine;
      if (ref.read(authSessionControllerProvider).isAuthenticated) {
        mine = await _loadMine(query);
      }
      if (!mounted) return;
      setState(() {
        _reviews = page.items;
        _nextCursor = page.nextCursor;
        _mine = mine;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.sectionLoad,
          scope: UiErrorScope.section,
        );
      });
    }
  }

  Future<HomepageReviewView?> _loadMine(HomepageReviewQuery query) async {
    try {
      return await query.getMine(
        MyHomepageReviewQuery(homepageId: widget.homepageId),
      );
    } on CloudException catch (error) {
      if (error.code == EntityErrorCode.reviewNotFound.code) {
        return null;
      }
      rethrow;
    } on HomepageReviewNotFoundException {
      return null;
    }
  }

  Future<void> _loadMore() async {
    final cursor = _nextCursor;
    if (cursor == null || _loading) return;
    try {
      final page = await ref
          .read(homepageReviewQueryProvider)
          .listByHomepage(
            HomepageReviewListQuery(
              homepageId: widget.homepageId,
              cursor: cursor,
            ),
          );
      if (!mounted) return;
      setState(() {
        _reviews = <HomepageReviewView>[..._reviews, ...page.items];
        _nextCursor = page.nextCursor;
      });
    } catch (error) {
      if (!mounted) return;
      final semantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.listAppend,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: semantic);
    }
  }

  Future<bool> _ensureAuth() async {
    final gate = widget.requireAuth;
    if (gate == null) return true;
    return gate();
  }

  Future<void> _openWriteSheet() async {
    if (_submitting || !await _ensureAuth() || !mounted) return;
    final existing = _mine;
    final draft = await showHomepageReviewSheet(
      context,
      initial: existing,
      tagOptions: widget.tagOptions,
    );
    if (draft == null || !mounted) return;
    setState(() => _submitting = true);
    try {
      final writer = ref.read(homepageReviewCommandWriterProvider);
      final isUpdate =
          existing != null && existing.status == HomepageReviewStatus.active;
      if (isUpdate) {
        await writer.update(
          UpdateHomepageReviewCommand(
            reviewId: existing.id,
            rating: draft.rating,
            body: draft.body,
            tagRefs: draft.tagRefs,
          ),
        );
      } else {
        await writer.create(
          CreateHomepageReviewCommand(
            homepageId: widget.homepageId,
            rating: draft.rating,
            body: draft.body,
            tagRefs: draft.tagRefs,
          ),
        );
      }
      if (!mounted) return;
      AppToast.show(
        context,
        isUpdate
            ? ObjectHomepageText.homepageReviewUpdated
            : ObjectHomepageText.homepageReviewSubmitted,
      );
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'entity_homepage',
              action: isUpdate ? 'review_update' : 'review_submit',
              pageName: 'homepageDetail',
              entityId: widget.homepageId,
              payload: const <String, dynamic>{'result': 'success'},
            ),
      );
      widget.onReviewsChanged?.call();
      await _load();
    } catch (error) {
      if (!mounted) return;
      final semantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: semantic);
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  void _scheduleReviewContinuationResume() {
    if (_continuationResumeScheduled || !mounted) {
      return;
    }
    _continuationResumeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _continuationResumeScheduled = false;
      if (!mounted) {
        return;
      }
      unawaited(_resumeReviewContinuation());
    });
  }

  Future<void> _resumeReviewContinuation() async {
    final controller = ref.read(authContinuationProvider.notifier);
    final pending = controller.take<OpenHomepageReviewComposerContinuation>();
    if (pending == null) {
      return;
    }
    if (pending.homepageId != widget.homepageId) {
      controller.set(pending);
      return;
    }
    await _load();
    if (mounted) {
      await _openWriteSheet();
    }
  }

  Future<void> _deleteMine() async {
    final mine = _mine;
    if (mine == null || _submitting || !await _ensureAuth() || !mounted) {
      return;
    }
    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (context) => CupertinoAlertDialog(
        title: Text(ObjectHomepageText.homepageReviewDeleteConfirmTitle),
        content: Text(ObjectHomepageText.homepageReviewDeleteConfirmMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(FoundationText.cancel),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(ObjectHomepageText.homepageReviewDeleteAction),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _submitting = true);
    try {
      await ref
          .read(homepageReviewCommandWriterProvider)
          .delete(DeleteHomepageReviewCommand(reviewId: mine.id));
      if (!mounted) return;
      AppToast.show(context, ObjectHomepageText.homepageReviewDeleted);
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'entity_homepage',
              action: 'review_delete',
              pageName: 'homepageDetail',
              entityId: widget.homepageId,
              payload: const <String, dynamic>{'result': 'success'},
            ),
      );
      widget.onReviewsChanged?.call();
      await _load();
    } catch (error) {
      if (!mounted) return;
      final semantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: semantic);
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return AppRequestFeedback.section();
    }
    if (_errorSemantic case final semantic?) {
      return AppSectionErrorState(
        semantic: semantic,
        onAction: (_) async => _load(),
      );
    }
    final mine = _mine;
    final mineActive =
        mine != null && mine.status == HomepageReviewStatus.active;
    final others = _reviews
        .where((review) => review.id != mine?.id)
        .toList(growable: false);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                ObjectHomepageText.homepageReviewSectionTitle,
                style: TextStyle(
                  fontSize: AppTypography.iosTitle3,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosLabel(context),
                ),
              ),
            ),
            CupertinoButton(
              key: const ValueKey<String>('homepage-review-write-entry'),
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: _submitting
                  ? null
                  : () => unawaited(_openWriteSheet()),
              child: Text(
                mineActive
                    ? ObjectHomepageText.homepageReviewEditAction
                    : ObjectHomepageText.homepageReviewWriteAction,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: AppColors.primaryColor,
                ),
              ),
            ),
          ],
        ),
        SizedBox(height: AppSpacing.containerSm),
        if (mineActive) ...<Widget>[
          ProfileIosSectionCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(
                        ObjectHomepageText.homepageReviewMineLabel,
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: AppColors.iosSecondaryLabel(context),
                        ),
                      ),
                    ),
                    CupertinoButton(
                      key: const ValueKey<String>(
                        'homepage-review-delete-entry',
                      ),
                      padding: EdgeInsets.zero,
                      minimumSize: Size.zero,
                      onPressed: _submitting
                          ? null
                          : () => unawaited(_deleteMine()),
                      child: Icon(
                        CupertinoIcons.trash,
                        size: AppSpacing.iconMedium,
                        color: AppColors.error,
                      ),
                    ),
                  ],
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                _HomepageReviewTile(review: mine),
              ],
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
        ],
        if (others.isEmpty && !mineActive)
          ProfileIosSectionCard(child: _HomepageReviewEmptyState())
        else ...<Widget>[
          for (final review in others)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.containerSm),
              child: ProfileIosSectionCard(
                child: _HomepageReviewTile(review: review),
              ),
            ),
          if (_nextCursor != null)
            CupertinoButton(
              onPressed: () => unawaited(_loadMore()),
              child: Text(FoundationText.myFootprintLoadMore),
            ),
        ],
      ],
    );
  }
}

final class _HomepageReviewTile extends StatelessWidget {
  const _HomepageReviewTile({required this.review});

  final HomepageReviewView review;

  @override
  Widget build(BuildContext context) {
    final displayName = review.authorDisplayNameSnapshot?.trim();
    final body = review.body?.trim();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                displayName?.isNotEmpty == true
                    ? displayName!
                    : ObjectHomepageText.homepageReviewAnonymousAuthor,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.medium,
                  color: AppColors.iosLabel(context),
                ),
              ),
            ),
            Row(
              children: List<Widget>.generate(5, (index) {
                return Icon(
                  index < review.rating
                      ? CupertinoIcons.star_fill
                      : CupertinoIcons.star,
                  size: AppSpacing.iconSmall,
                  color: index < review.rating
                      ? AppColors.warning
                      : AppColors.iosTertiaryLabel(context),
                );
              }),
            ),
          ],
        ),
        if (body != null && body.isNotEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            body,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              color: AppColors.iosLabel(context),
            ),
          ),
        ],
        if ((review.tagRefs ?? const <String>[]).isNotEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupXs),
          Wrap(
            spacing: AppSpacing.intraGroupXs,
            runSpacing: AppSpacing.intraGroupXs,
            children: tagRefDisplayLabels(review.tagRefs ?? const <String>[])
                .map(
                  (label) => Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                      vertical: AppSpacing.intraGroupXs / 2,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.iosSecondaryFill(context),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.circularBorderRadius,
                      ),
                    ),
                    child: Text(
                      label,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ),
                )
                .toList(growable: false),
          ),
        ],
      ],
    );
  }
}

final class _HomepageReviewEmptyState extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(
      children: <Widget>[
        Icon(
          CupertinoIcons.star,
          size: AppSpacing.iconLarge,
          color: AppColors.iosTertiaryLabel(context),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Text(
          ObjectHomepageText.homepageReviewEmptyTitle,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            fontWeight: AppTypography.medium,
            color: AppColors.iosLabel(context),
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupXs),
        Text(
          ObjectHomepageText.homepageReviewEmptyDescription,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ],
    );
  }
}
