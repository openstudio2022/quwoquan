import 'dart:async';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';

import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/ios_selection_page_components.dart';
import 'package:quwoquan_app/design_system/search/app_search_field.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show homepageQueryProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/runtime/observability/trackers/homepage_product_action_tracker.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_route_models.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_type_labels.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';

class HomepagePickerPage extends ConsumerStatefulWidget {
  const HomepagePickerPage({
    super.key,
    this.initialQuery = '',
    this.initialSelection,
  });

  final String initialQuery;
  final HomepageCanonicalReference? initialSelection;

  @override
  ConsumerState<HomepagePickerPage> createState() => _HomepagePickerPageState();
}

class _HomepagePickerPageState extends ConsumerState<HomepagePickerPage> {
  static const Duration _queryDebounce = Duration(milliseconds: 220);

  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  Timer? _debounceTimer;
  int _requestToken = 0;
  String _query = '';
  bool _isLoading = false;
  UiErrorSemantic? _errorSemantic;
  List<HomepageSummary> _results = const <HomepageSummary>[];
  HomepageCanonicalReference? _selected;

  @override
  void initState() {
    super.initState();
    _query = widget.initialQuery.trim();
    _selected = widget.initialSelection;
    _controller = TextEditingController(text: _query);
    _focusNode = FocusNode();
    _scheduleRefresh(immediate: true);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _focusNode.requestFocus();
      }
    });
  }

  @override
  void dispose() {
    _debounceTimer?.cancel();
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IosSelectionPageScaffold(
      pageKey: TestKeys.homepagePickerPage,
      title: CreationText.attachHomepageTitle,
      onBack: () => Navigator.of(context).pop(),
      backgroundColor: AppColors.iosPageBackground(context),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerXs,
              AppSpacing.containerMd,
              AppSpacing.intraGroupSm,
            ),
            child: AppSearchField(
              key: TestKeys.homepagePickerSearchField,
              controller: _controller,
              focusNode: _focusNode,
              placeholder: CreationText.attachHomepageSearchHint,
              onChanged: (value) {
                setState(() {
                  _query = value.trim();
                });
                _scheduleRefresh();
              },
              onSubmitted: (_) => _scheduleRefresh(immediate: true),
            ),
          ),
          Expanded(child: _buildBody(AppColors.iosSecondaryLabel(context))),
        ],
      ),
      bottomBar: IosSelectionBottomBar(
        cancelButtonKey: TestKeys.homepagePickerCancelButton,
        confirmButtonKey: TestKeys.homepagePickerConfirmButton,
        onCancel: () => Navigator.of(context).pop(),
        onConfirm: _confirmSelection,
      ),
    );
  }

  Widget _buildBody(Color fgSecondary) {
    final selected = _selected;
    final selectedVisibleInResults =
        selected != null && _results.any((item) => item.id == selected.id);
    if (_isLoading && _results.isEmpty) {
      return _buildStatusSection(
        text: FoundationText.loading,
        fgSecondary: fgSecondary,
        loading: true,
      );
    }
    if (_errorSemantic != null && _results.isEmpty) {
      if (selected != null) {
        return _buildSelectedAndMessageSection(
          selected: selected,
          semantic: _errorSemantic!,
        );
      }
      return AppPageErrorState(
        semantic: _errorSemantic!,
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _loadResults();
            return _errorSemantic == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
    }
    if (_results.isEmpty) {
      if (selected != null) {
        return _buildSelectedAndMessageSection(
          selected: selected,
          semantic: UiErrorSemantic(
            category: UiErrorCategory.validation,
            scope: UiErrorScope.section,
            title: CreationText.attachHomepageTitle,
            message: CreationText.attachHomepageEmpty,
          ),
          showSuggestAction: true,
        );
      }
      return _buildEmptySection(fgSecondary);
    }

    return ListView(
      padding: EdgeInsets.only(bottom: AppSpacing.interGroupLg),
      children: <Widget>[
        if (selected != null && !selectedVisibleInResults) ...<Widget>[
          const IosSelectionSectionHeader(
            title: CreationText.attachHomepageCurrentSection,
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.intraGroupXs,
              AppSpacing.containerMd,
              AppSpacing.intraGroupXs,
            ),
          ),
          _buildSelectedReferenceTile(selected),
          const SizedBox(height: AppSpacing.interGroupSm),
        ],
        const IosSelectionSectionHeader(
          title: CreationText.attachHomepageResultsSection,
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.intraGroupXs,
            AppSpacing.containerMd,
            AppSpacing.intraGroupXs,
          ),
        ),
        for (var i = 0; i < _results.length; i++) ...<Widget>[
          _buildResultTile(_results[i]),
          if (i != _results.length - 1) _buildSectionDivider(),
        ],
        SizedBox(height: AppSpacing.containerSm),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
          child: CupertinoButton(
            key: TestKeys.homepagePickerSuggestButton,
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            alignment: Alignment.centerLeft,
            onPressed: _openSuggestPage,
            child: Text(
              _query.isEmpty
                  ? CreationText.attachHomepageSuggest
                  : UITextConstants.attachHomepageSuggestWithQuery(_query),
              style: TextStyle(
                color: AppColors.iosAccent(context),
                fontSize: AppTypography.iosFootnote,
                fontWeight: AppTypography.medium,
              ),
            ),
          ),
        ),
      ],
    );
  }

  void _scheduleRefresh({bool immediate = false}) {
    _debounceTimer?.cancel();
    if (immediate) {
      unawaited(_loadResults());
      return;
    }
    _debounceTimer = Timer(_queryDebounce, () => unawaited(_loadResults()));
  }

  Future<void> _loadResults() async {
    final startedAt = DateTime.now();
    final token = ++_requestToken;
    setState(() {
      _isLoading = true;
      _errorSemantic = null;
    });
    try {
      final items = await ref
          .read(homepageQueryProvider)
          .searchHomepages(query: _query.trim(), limit: 12);
      if (!mounted || token != _requestToken) {
        return;
      }
      setState(() {
        _results = items
            .where((item) => (item.status ?? 'published').trim() == 'published')
            .toList(growable: false);
        _isLoading = false;
      });
      await trackHomepageProductAction(
        ref.read(journeyEventTrackerProvider),
        action: 'picker_search',
        pageName: 'homepagePicker',
        result: 'success',
        startedAt: startedAt,
      );
    } catch (error) {
      if (!mounted || token != _requestToken) {
        return;
      }
      setState(() {
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
        _isLoading = false;
      });
      await trackHomepageProductAction(
        ref.read(journeyEventTrackerProvider),
        action: 'picker_search',
        pageName: 'homepagePicker',
        result: 'failure',
        startedAt: startedAt,
        error: error,
      );
    }
  }

  Widget _buildSelectedAndMessageSection({
    required HomepageCanonicalReference selected,
    required UiErrorSemantic semantic,
    bool showSuggestAction = false,
  }) {
    return ListView(
      padding: EdgeInsets.only(bottom: AppSpacing.interGroupLg),
      children: <Widget>[
        const IosSelectionSectionHeader(
          title: CreationText.attachHomepageCurrentSection,
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.intraGroupXs,
            AppSpacing.containerMd,
            AppSpacing.intraGroupXs,
          ),
        ),
        _buildSelectedReferenceTile(selected),
        SizedBox(height: AppSpacing.interGroupMd),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
          child: Column(
            children: <Widget>[
              AppSectionErrorCard(
                semantic: semantic,
                onAction: (action) async {
                  if (action.type == UiErrorActionType.retry ||
                      action.type == UiErrorActionType.resubmit) {
                    await _loadResults();
                  }
                },
              ),
              if (showSuggestAction) ...<Widget>[
                SizedBox(height: AppSpacing.interGroupMd),
                CupertinoButton(
                  key: TestKeys.homepagePickerSuggestButton,
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: _openSuggestPage,
                  child: Text(CreationText.attachHomepageSuggest),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSelectedReferenceTile(HomepageCanonicalReference selected) {
    return IosSelectionOptionTile(
      backgroundColor: AppColors.iosSystemBackground(context),
      pressedColor: AppColors.iosSecondaryFill(context),
      // canonical reference 只携带公开取值，投影未在此交出资产身份。
      leading: _buildHomepageCover(
        MediaDeliveryBinding(
          assetId: '',
          accessMode: null,
          publicUrl: selected.coverUrl ?? '',
        ),
      ),
      title: Text(
        selected.title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: AppTypography.iosSubheadline,
          fontWeight: AppTypography.medium,
          color: AppColors.iosLabel(context),
        ),
      ),
      subtitle: Text(
        [
          homepageTypeLabel(selected.homepageType),
          if ((selected.subtitle ?? '').trim().isNotEmpty)
            selected.subtitle!.trim(),
        ].join(' · '),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
      trailing: _buildSelectionIndicator(checked: true),
      onTap: () {
        setState(() {
          _selected = null;
        });
      },
    );
  }

  Widget _buildResultTile(HomepageSummary summary) {
    final checked = _selected?.id == summary.id;
    return IosSelectionOptionTile(
      key: ValueKey<String>('homepage_picker_result_${summary.id}'),
      backgroundColor: AppColors.iosSystemBackground(context),
      pressedColor: AppColors.iosSecondaryFill(context),
      leading: _buildHomepageCover(
        MediaDeliveryBinding(
          assetId: summary.coverAssetId?.trim() ?? '',
          accessMode: summary.coverAccessMode,
          publicUrl: summary.coverUrl ?? '',
        ),
      ),
      title: Text(
        summary.title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: AppTypography.iosSubheadline,
          fontWeight: AppTypography.medium,
          color: AppColors.iosLabel(context),
        ),
      ),
      subtitle: Text(
        _buildSummaryLine(summary),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
      trailing: _buildSelectionIndicator(checked: checked),
      onTap: () {
        setState(() {
          _selected = checked ? null : summary.canonicalReference;
        });
      },
    );
  }

  Widget _buildHomepageCover(MediaDeliveryBinding binding) {
    final fallback = _buildPlaceholderCover(
      icon: CupertinoIcons.photo_fill_on_rectangle_fill,
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(
        AppSpacing.contentPreviewCornerRadius,
      ),
      child: SizedBox(
        width: AppSpacing.avatarUserLg,
        height: AppSpacing.avatarUserLg,
        // 交付形态取自搜索投影声明（DEC-033），不从 URL 形态反推。
        child: mediaDeliveryImage(
          binding: binding,
          kind: MediaDeliveryKind.image,
          fit: BoxFit.cover,
          placeholder: fallback,
          errorWidget: fallback,
          absentWidget: fallback,
          publicBuilder: (context, publicUrl) => AppMediaImage(
            imageSource: publicUrl,
            fit: BoxFit.cover,
            placeholder: fallback,
            errorWidget: fallback,
          ),
        ),
      ),
    );
  }

  Widget _buildPlaceholderCover({required IconData icon}) {
    return ColoredBox(
      color: AppColors.iosSecondaryFill(context),
      child: Center(
        child: Icon(icon, color: AppColors.iosSecondaryLabel(context)),
      ),
    );
  }

  Widget _buildSelectionIndicator({required bool checked}) {
    return SizedBox(
      width: AppSpacing.minInteractiveSize,
      height: AppSpacing.minInteractiveSize,
      child: Center(
        child: Icon(
          checked
              ? CupertinoIcons.check_mark_circled_solid
              : CupertinoIcons.circle,
          size: AppSpacing.iconMedium,
          color: checked
              ? AppColors.primaryColor
              : CupertinoColors.systemGrey2.resolveFrom(context),
        ),
      ),
    );
  }

  Widget _buildSectionDivider() {
    return const IosSelectionInlineDivider(
      indent:
          AppSpacing.containerMd +
          AppSpacing.avatarUserLg +
          AppSpacing.containerSm,
      endIndent: AppSpacing.containerMd,
    );
  }

  Widget _buildStatusSection({
    required String text,
    required Color fgSecondary,
    bool loading = false,
  }) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: IosSelectionSection(
          addShadow: false,
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.containerLg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (loading) AppRequestFeedback.inline(),
                if (loading) SizedBox(height: AppSpacing.intraGroupSm),
                Text(
                  text,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildEmptySection(Color fgSecondary) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: IosSelectionSection(
          addShadow: false,
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.containerLg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  CreationText.attachHomepageEmpty,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    color: fgSecondary,
                    height: AppTypography.bodyLineHeight,
                  ),
                ),
                SizedBox(height: AppSpacing.interGroupMd),
                CupertinoButton(
                  key: TestKeys.homepagePickerSuggestButton,
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: _openSuggestPage,
                  child: Text(CreationText.attachHomepageSuggest),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _buildSummaryLine(HomepageSummary summary) {
    final typeLabel = homepageTypeLabel(summary.homepageType);
    final detail = (summary.subtitle ?? '').trim().isNotEmpty
        ? summary.subtitle!.trim()
        : <String>[
            if ((summary.city ?? '').trim().isNotEmpty) summary.city!.trim(),
            if ((summary.address ?? '').trim().isNotEmpty)
              summary.address!.trim(),
          ].join(' · ');
    final rating = summary.averageRating;
    final ratingSummary = rating == null || summary.ratingCount <= 0
        ? ''
        : '${rating.toStringAsFixed(1)} · '
              '${UITextConstants.homepageRatingCount(summary.ratingCount)}';
    return <String>[
      typeLabel,
      if (detail.isNotEmpty) detail,
      if (ratingSummary.isNotEmpty) ratingSummary,
    ].join(' · ');
  }

  Future<void> _openSuggestPage() async {
    final submitted = await context.push<bool>(
      AppRoutePaths.suggestHomepage(
        query: _query.trim().isEmpty ? null : _query,
      ),
    );
    if (submitted == true && mounted) {
      AppToast.show(context, CreationText.addHomepageSubmitted);
      _scheduleRefresh(immediate: true);
    }
  }

  void _confirmSelection() {
    final startedAt = DateTime.now();
    unawaited(
      trackHomepageProductAction(
        ref.read(journeyEventTrackerProvider),
        action: 'picker_confirm',
        pageName: 'homepagePicker',
        result: 'success',
        startedAt: startedAt,
        homepageId: _selected?.id ?? '',
      ),
    );
    Navigator.of(context).pop(
      _selected == null
          ? const HomepagePickerSelectionResult.clear()
          : HomepagePickerSelectionResult.selected(_selected!),
    );
  }
}
