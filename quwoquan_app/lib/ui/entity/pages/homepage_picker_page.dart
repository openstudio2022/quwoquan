import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';

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
  String? _errorText;
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
      title: UITextConstants.attachHomepageTitle,
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
              placeholder: UITextConstants.attachHomepageSearchHint,
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
        onConfirm: () => Navigator.of(context).pop(
          _selected == null
              ? const HomepagePickerSelectionResult.clear()
              : HomepagePickerSelectionResult.selected(_selected!),
        ),
      ),
    );
  }

  Widget _buildBody(Color fgSecondary) {
    final selected = _selected;
    final selectedVisibleInResults =
        selected != null && _results.any((item) => item.id == selected.id);
    if (_isLoading && _results.isEmpty) {
      return _buildStatusSection(
        text: UITextConstants.loading,
        fgSecondary: fgSecondary,
        loading: true,
      );
    }
    if (_errorText != null && _results.isEmpty) {
      if (selected != null) {
        return _buildSelectedAndMessageSection(
          selected: selected,
          text: _errorText!,
          fgSecondary: fgSecondary,
        );
      }
      return _buildStatusSection(text: _errorText!, fgSecondary: fgSecondary);
    }
    if (_results.isEmpty) {
      if (selected != null) {
        return _buildSelectedAndMessageSection(
          selected: selected,
          text: UITextConstants.attachHomepageEmpty,
          fgSecondary: fgSecondary,
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
            title: '当前关联',
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
          title: '搜索结果',
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
                  ? UITextConstants.attachHomepageSuggest
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
    final token = ++_requestToken;
    setState(() {
      _isLoading = true;
      _errorText = null;
    });
    try {
      final items = await ref
          .read(homepageRepositoryProvider)
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
    } catch (_) {
      if (!mounted || token != _requestToken) {
        return;
      }
      setState(() {
        _errorText = UITextConstants.attachHomepageUnavailable;
        _isLoading = false;
      });
    }
  }

  Widget _buildSelectedAndMessageSection({
    required HomepageCanonicalReference selected,
    required String text,
    required Color fgSecondary,
    bool showSuggestAction = false,
  }) {
    return ListView(
      padding: EdgeInsets.only(bottom: AppSpacing.interGroupLg),
      children: <Widget>[
        const IosSelectionSectionHeader(
          title: '当前关联',
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
          child: IosSelectionSection(
            addShadow: false,
            child: Padding(
              padding: EdgeInsets.all(AppSpacing.containerLg),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    text,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      color: fgSecondary,
                      height: AppTypography.bodyLineHeight,
                    ),
                  ),
                  if (showSuggestAction) ...<Widget>[
                    SizedBox(height: AppSpacing.interGroupMd),
                    CupertinoButton(
                      key: TestKeys.homepagePickerSuggestButton,
                      padding: EdgeInsets.zero,
                      minimumSize: Size.zero,
                      onPressed: _openSuggestPage,
                      child: Text(UITextConstants.attachHomepageSuggest),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSelectedReferenceTile(HomepageCanonicalReference selected) {
    return IosSelectionOptionTile(
      backgroundColor: AppColors.iosSystemBackground(context),
      pressedColor: AppColors.iosSecondaryFill(context),
      leading: _buildHomepageCover(selected.coverUrl),
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
          _homepageTypeLabel(selected.homepageType),
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
      leading: _buildHomepageCover(summary.coverUrl),
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

  Widget _buildHomepageCover(String? coverUrl) {
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
        child: (coverUrl ?? '').trim().isEmpty
            ? fallback
            : CircleMediaImage(
                imageSource: coverUrl!,
                fit: BoxFit.cover,
                placeholder: fallback,
                errorWidget: fallback,
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
                if (loading) const CupertinoActivityIndicator(),
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
                  UITextConstants.attachHomepageEmpty,
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
                  child: Text(UITextConstants.attachHomepageSuggest),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _buildSummaryLine(HomepageSummary summary) {
    final typeLabel = _homepageTypeLabel(summary.homepageType);
    final detail = (summary.subtitle ?? '').trim().isNotEmpty
        ? summary.subtitle!.trim()
        : <String>[
            if ((summary.city ?? '').trim().isNotEmpty) summary.city!.trim(),
            if ((summary.address ?? '').trim().isNotEmpty)
              summary.address!.trim(),
          ].join(' · ');
    return detail.isEmpty ? typeLabel : '$typeLabel · $detail';
  }

  Future<void> _openSuggestPage() async {
    final submitted = await context.push<bool>(
      AppRoutePaths.suggestHomepage(
        query: _query.trim().isEmpty ? null : _query,
      ),
    );
    if (submitted == true && mounted) {
      AppToast.show(context, UITextConstants.addHomepageSubmitted);
      _scheduleRefresh(immediate: true);
    }
  }
}

String _homepageTypeLabel(String type) {
  switch (type.trim()) {
    case 'hotel':
      return '酒店';
    case 'restaurant':
      return '餐厅';
    case 'vehicle':
      return '车型';
    case 'sight':
      return '景点';
    default:
      return '主页';
  }
}
