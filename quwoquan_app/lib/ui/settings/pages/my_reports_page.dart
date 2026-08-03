import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/components/content/content_time_label.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/core/widgets/content_report_reason_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 当前 persona 私有可见的举报生命周期列表。
class MyReportsPage extends ConsumerStatefulWidget {
  const MyReportsPage({super.key});

  @override
  ConsumerState<MyReportsPage> createState() => _MyReportsPageState();
}

class _MyReportsPageState extends ConsumerState<MyReportsPage> {
  final List<MyReportItemSlice> _items = <MyReportItemSlice>[];
  String? _nextCursor;
  Object? _rawError;
  bool _loading = false;
  bool _loadingMore = false;
  late final PageLifecycleObservability _pageObservability;
  late final DateTime _enteredAt;

  void _recordPageState({
    required String phase,
    Object? error,
    int? itemCount,
  }) {
    _pageObservability.recordPageState(
      pageName: 'MyReportsPage',
      route: AppRoutePaths.myReports,
      surface: AppUiSurfaces.myReports.id,
      phase: phase,
      error: error,
      itemCount: itemCount,
      durationMs: phase == 'exit'
          ? DateTime.now().difference(_enteredAt).inMilliseconds
          : null,
    );
  }

  @override
  void initState() {
    super.initState();
    _pageObservability = ref.read(pageLifecycleObservabilityProvider);
    _enteredAt = DateTime.now();
    _recordPageState(phase: 'enter');
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      unawaited(_load(reset: true));
    }
  }

  Future<void> _load({required bool reset}) async {
    if (_loading || _loadingMore) return;
    setState(() {
      if (reset) {
        _loading = true;
        _rawError = null;
      } else {
        _loadingMore = true;
      }
    });
    _recordPageState(phase: 'onlineLoading');
    try {
      final page = await ref
          .read(myReportsContentReportQueryProvider)
          .listMyReports(
            ContentMyReportsQuery(
              cursor: reset ? null : _nextCursor,
              limit: 20,
            ),
          );
      if (!mounted) return;
      setState(() {
        if (reset) {
          _items
            ..clear()
            ..addAll(page.items);
        } else {
          _items.addAll(page.items);
        }
        _nextCursor = page.nextCursor;
        _rawError = null;
      });
      _recordPageState(
        phase: _items.isEmpty ? 'emptyState' : 'onlineSuccess',
        itemCount: _items.length,
      );
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'content_report',
              action: 'list_my_reports',
              pageName: 'MyReportsPage',
              payload: <String, Object?>{
                'result': 'success',
                'resultCount': page.items.length,
              },
            ),
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _rawError = error);
      _recordPageState(phase: 'blockingFailure', error: error);
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'content_report',
              action: 'list_my_reports',
              pageName: 'MyReportsPage',
              payload: <String, Object?>{
                'result': 'failure',
                'failReasonCode': error is CloudException
                    ? (error.code ?? error.type.name)
                    : error.runtimeType.toString(),
              },
            ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _loadingMore = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _recordPageState(phase: 'exit', itemCount: _items.length);
    super.dispose();
  }

  Future<void> _requestLogin() {
    return requireLogin(
      ref,
      context,
      AuthGateReason.report,
      redirect: AppRoutePaths.myReports,
      dismissFallback: AppRoutePaths.settings,
      dismissPolicy: LoginDismissPolicy.safeFallback,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final isAuthenticated = ref.watch(
      authSessionControllerProvider.select((state) => state.isAuthenticated),
    );
    ref.listen<bool>(
      authSessionControllerProvider.select((state) => state.isAuthenticated),
      (previous, next) {
        if (next && previous != true && _items.isEmpty) {
          unawaited(_load(reset: true));
        }
      },
    );
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: ContentText.myReportsTitle,
      onBack: () {
        if (context.canPop()) {
          context.pop();
        } else {
          context.go(AppRoutePaths.settings);
        }
      },
      body: WebPageMaxWidthFrame(
        child: SafeArea(
          bottom: false,
          child: isAuthenticated
              ? _buildAuthenticatedBody(isDark)
              : _buildLoginRequired(),
        ),
      ),
    );
  }

  Widget _buildAuthenticatedBody(bool isDark) {
    if (_loading && _items.isEmpty) {
      return AppRequestFeedback.section();
    }
    if (_rawError case final error? when _items.isEmpty) {
      return AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry) {
            await _load(reset: true);
          }
        },
      );
    }
    if (_items.isEmpty) {
      return const _MyReportsEmptyState();
    }
    return ListView(
      padding: EdgeInsets.only(
        left: SettingsSemanticConstants.insetFormListHorizontalPadding,
        right: SettingsSemanticConstants.insetFormListHorizontalPadding,
        top: AppSpacing.intraGroupSm,
        bottom: AppSpacing.xl,
      ),
      children: <Widget>[
        SettingsInsetGroupedSection(
          isDark: isDark,
          density: SettingsInsetSectionDensity.compact,
          child: Column(
            children: <Widget>[
              for (var index = 0; index < _items.length; index += 1) ...[
                _MyReportRow(item: _items[index], isDark: isDark),
                if (index != _items.length - 1)
                  SettingsInsetFormSectionDivider(isDark: isDark),
              ],
            ],
          ),
        ),
        if (_nextCursor != null || _loadingMore)
          Padding(
            padding: EdgeInsets.only(top: AppSpacing.interGroupMd),
            child: Center(
              child: _loadingMore
                  ? AppRequestFeedback.inline()
                  : CupertinoButton(
                      onPressed: () => _load(reset: false),
                      child: const Text(ContentText.loadMore),
                    ),
            ),
          ),
      ],
    );
  }

  Widget _buildLoginRequired() {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.flag_circle,
              size: AppSpacing.iconLarge,
              color: AppColors.iosSecondaryLabel(context),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Text(
              ContentText.myReportsLoginTitle,
              style: TextStyle(
                color: AppColors.iosLabel(context),
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              ContentText.myReportsLoginSubtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.iosSubheadline,
              ),
            ),
            SizedBox(height: AppSpacing.interGroupLg),
            CupertinoButton.filled(
              onPressed: _requestLogin,
              child: const Text(FoundationText.profileLoginNow),
            ),
          ],
        ),
      ),
    );
  }
}

class _MyReportRow extends StatelessWidget {
  const _MyReportRow({required this.item, required this.isDark});

  final MyReportItemSlice item;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        vertical: SettingsSemanticConstants.insetFormRowVerticalPadding,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            _statusIcon(item.status),
            size: AppSpacing.iconMedium,
            color: AppColors.iosSecondaryLabel(context),
          ),
          SizedBox(width: AppSpacing.interGroupSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(
                        '${_targetLabel(item.targetType)} · '
                        '${contentReportReasonLabel(item.reason)}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: SettingsSemanticConstants.labelColor(isDark),
                          fontSize: AppTypography.iosBody,
                          fontWeight: AppTypography.medium,
                        ),
                      ),
                    ),
                    SizedBox(width: AppSpacing.intraGroupSm),
                    Text(
                      _statusLabel(item.status),
                      style: TextStyle(
                        color: AppColors.iosSecondaryLabel(context),
                        fontSize: AppTypography.iosFootnote,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                  ],
                ),
                if (item.description case final description?
                    when description.isNotEmpty) ...<Widget>[
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    description,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: AppColors.iosSecondaryLabel(context),
                      fontSize: AppTypography.iosSubheadline,
                    ),
                  ),
                ],
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  ContentTimeLabel.relative(item.updatedAt),
                  style: TextStyle(
                    color: AppColors.iosTertiaryLabel(context),
                    fontSize: AppTypography.iosFootnote,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String _targetLabel(ReportTargetType type) {
    return switch (type) {
      ReportTargetType.post => ContentText.reportTargetPost,
      ReportTargetType.comment => ContentText.reportTargetComment,
      ReportTargetType.user => ContentText.reportTargetUser,
      ReportTargetType.circle => ContentText.reportTargetCircle,
      ReportTargetType.message => ContentText.reportTargetMessage,
    };
  }

  static String _statusLabel(ReportStatus status) {
    return switch (status) {
      ReportStatus.pending => ContentText.reportStatusPending,
      ReportStatus.reviewing => ContentText.reportStatusReviewing,
      ReportStatus.resolved => ContentText.reportStatusResolved,
      ReportStatus.dismissed => ContentText.reportStatusDismissed,
    };
  }

  static IconData _statusIcon(ReportStatus status) {
    return switch (status) {
      ReportStatus.pending => CupertinoIcons.clock,
      ReportStatus.reviewing => CupertinoIcons.doc_text_search,
      ReportStatus.resolved => CupertinoIcons.check_mark_circled,
      ReportStatus.dismissed => CupertinoIcons.info_circle,
    };
  }
}

class _MyReportsEmptyState extends StatelessWidget {
  const _MyReportsEmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.flag,
              size: AppSpacing.iconLarge,
              color: AppColors.iosSecondaryLabel(context),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            Text(
              ContentText.myReportsEmptyTitle,
              style: TextStyle(
                color: AppColors.iosLabel(context),
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              ContentText.myReportsEmptySubtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.iosSubheadline,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
