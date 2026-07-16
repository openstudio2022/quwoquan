import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/application/circle/membership/persona_circle_summary_mapper.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class ContentCircleSharePickerRoute extends ConsumerStatefulWidget {
  const ContentCircleSharePickerRoute({
    super.key,
    required this.postId,
    required this.placementWriter,
    required this.membershipQuery,
  });

  final String postId;
  final CirclePostPlacementCommandWriter placementWriter;
  final CircleMembershipQuery membershipQuery;

  @override
  ConsumerState<ContentCircleSharePickerRoute> createState() =>
      _ContentCircleSharePickerRouteState();
}

class _ContentCircleSharePickerRouteState
    extends ConsumerState<ContentCircleSharePickerRoute> {
  final TextEditingController _searchController = TextEditingController();
  late Future<List<CircleDto>> _future;
  String _query = '';
  String? _busyCircleId;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<List<CircleDto>> _load() async {
    final ownerUserId = ref.read(resolvedOwnerUserIdProvider).trim();
    if (ownerUserId.isEmpty) {
      throw StateError(UITextConstants.needLogin);
    }
    final persona = await ref.read(activePersonaContextProvider.future);
    final page = await widget.membershipQuery.listPersonaCircles(
      PersonaCircleListQuery(personaId: persona.subAccountId, limit: 100),
    );
    final circles = page.items
        .map(circleDtoFromPersonaCircleSummary)
        .toList(growable: false);
    final active = circles
        .where((circle) => circle.status.trim().toLowerCase() == 'active')
        .toList(growable: false);
    active.sort((a, b) => a.name.compareTo(b.name));
    return active;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: UITextConstants.shareSelectCircleTitle,
      onBack: () => Navigator.of(context).pop(false),
      body: Column(
        children: <Widget>[
          Padding(
            padding: EdgeInsets.fromLTRB(
              SettingsSemanticConstants.blockHorizontalPadding,
              AppSpacing.containerMd,
              SettingsSemanticConstants.blockHorizontalPadding,
              AppSpacing.containerSm,
            ),
            child: AppSearchField(
              controller: _searchController,
              placeholder: UITextConstants.search,
              elevated: false,
              onChanged: (value) => setState(() => _query = value.trim()),
            ),
          ),
          Expanded(
            child: FutureBuilder<List<CircleDto>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CupertinoActivityIndicator());
                }
                if (snapshot.hasError) {
                  final semantic = runtimeErrorSemantic(
                    context,
                    error:
                        snapshot.error ??
                        StateError(UITextConstants.loadFailed),
                    category: UiErrorCategory.sectionLoad,
                    scope: UiErrorScope.section,
                  );
                  return AppSectionErrorState(
                    semantic: semantic,
                    onAction: (action) async {
                      if (action.type == UiErrorActionType.retry ||
                          action.type == UiErrorActionType.resubmit) {
                        setState(() => _future = _load());
                      }
                    },
                  );
                }
                final normalizedQuery = _query.toLowerCase();
                final circles = (snapshot.data ?? const <CircleDto>[])
                    .where(
                      (circle) =>
                          normalizedQuery.isEmpty ||
                          circle.name.toLowerCase().contains(normalizedQuery) ||
                          (circle.description ?? '').toLowerCase().contains(
                            normalizedQuery,
                          ),
                    )
                    .toList(growable: false);
                if (circles.isEmpty) {
                  return Center(
                    child: Text(
                      UITextConstants.shareNoCircles,
                      style: TextStyle(
                        fontSize: AppTypography.iosBody,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  );
                }
                return _CircleList(
                  circles: circles,
                  busyCircleId: _busyCircleId,
                  onTap: _confirmShare,
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmShare(CircleDto circle) async {
    if (_busyCircleId != null) {
      return;
    }
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(UITextConstants.shareCircleConfirmTitle(circle.name)),
        content: const Text(UITextConstants.shareCircleConfirmMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(UITextConstants.cancel),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(UITextConstants.confirm),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      await _submit(circle);
    }
  }

  Future<void> _submit(CircleDto circle) async {
    setState(() => _busyCircleId = circle.id);
    try {
      await widget.placementWriter.placePost(
        PlaceCirclePostCommand(circleId: circle.id, postId: widget.postId),
      );
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.shareCircleSuccess);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _busyCircleId = null);
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: UiErrorSemantic(
          category: resolved.category,
          scope: resolved.scope,
          title: UITextConstants.shareCircleFailedTitle,
          message: resolved.message,
          secondaryMessage: resolved.secondaryMessage,
          primaryAction: resolved.primaryAction,
          secondaryAction: resolved.secondaryAction,
          dismissible: resolved.dismissible,
          sourceCode: resolved.sourceCode,
          failureKind: resolved.failureKind,
          copyKey: resolved.copyKey,
          recoveryAction: resolved.recoveryAction,
          presentation: resolved.presentation,
          tone: resolved.tone,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submit(circle);
          }
        },
      );
    }
  }
}

class _CircleList extends StatelessWidget {
  const _CircleList({
    required this.circles,
    required this.busyCircleId,
    required this.onTap,
  });

  final List<CircleDto> circles;
  final String? busyCircleId;
  final ValueChanged<CircleDto> onTap;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.blockHorizontalPadding,
        AppSpacing.containerSm,
        SettingsSemanticConstants.blockHorizontalPadding,
        AppSpacing.containerXl,
      ),
      itemCount: circles.length,
      separatorBuilder: (_, _) => SizedBox(height: AppSpacing.intraGroupSm),
      itemBuilder: (context, index) {
        final circle = circles[index];
        final busy = busyCircleId == circle.id;
        return DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.iosSystemBackground(context),
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          child: CupertinoButton(
            padding: EdgeInsets.all(AppSpacing.containerSm),
            onPressed: busyCircleId == null ? () => onTap(circle) : null,
            child: Row(
              children: <Widget>[
                RoundedSquareAvatar(
                  size: AppSpacing.largeButtonSize,
                  imageUrl: circle.iconUrl ?? circle.coverUrl ?? '',
                  name: circle.name,
                ),
                SizedBox(width: AppSpacing.containerSm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        circle.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosBody,
                          fontWeight: AppTypography.medium,
                          color: AppColors.iosLabel(context),
                        ),
                      ),
                      if ((circle.description ?? '').trim().isNotEmpty) ...[
                        SizedBox(height: AppSpacing.intraGroupXs),
                        Text(
                          circle.description!.trim(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: AppColors.iosSecondaryLabel(context),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (busy)
                  const CupertinoActivityIndicator()
                else
                  Icon(
                    CupertinoIcons.chevron_forward,
                    size: AppSpacing.iconMedium,
                    color: AppColors.iosTertiaryLabel(context),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
