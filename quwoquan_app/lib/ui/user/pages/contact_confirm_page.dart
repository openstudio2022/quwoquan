import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/models/contact_candidate_vm.dart';

/// 添加联系人确认页：展示目标用户资料与来源，统一以 follow 语义完成「添加」。
class ContactConfirmPage extends ConsumerStatefulWidget {
  const ContactConfirmPage({
    super.key,
    required this.targetUserId,
    this.handle = '',
    this.source = '',
  });

  final String targetUserId;
  final String handle;
  final String source;

  @override
  ConsumerState<ContactConfirmPage> createState() => _ContactConfirmPageState();
}

class _ContactConfirmPageState extends ConsumerState<ContactConfirmPage> {
  late Future<_ConfirmData> _future;
  bool _adding = false;
  ContactAddState? _localAddState;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_ConfirmData> _load() async {
    final repo = ref.read(userProfileRepositoryProvider);
    final profile = await repo.getSubAccountProfile(widget.targetUserId);
    final capability = await ref
        .read(relationshipCapabilityRepositoryProvider)
        .getCapability(widget.targetUserId);
    return _ConfirmData(profile: profile, capability: capability);
  }

  void _reload() {
    setState(() {
      _localAddState = null;
      _future = _load();
    });
  }

  Future<void> _add(ContactAddState addState) async {
    if (_adding || !addState.canTriggerAdd) {
      return;
    }
    setState(() => _adding = true);
    try {
      await ref
          .read(userProfileRepositoryProvider)
          .followUser(widget.targetUserId);
      if (!mounted) {
        return;
      }
      setState(() => _localAddState = ContactAddState.added);
      AppToast.show(context, UITextConstants.addContactConfirmedToast);
    } catch (error) {
      if (!mounted) {
        return;
      }
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _add(addState);
          }
        },
      );
    } finally {
      if (mounted) {
        setState(() => _adding = false);
      }
    }
  }

  String get _sourceLabel {
    switch (widget.source) {
      case 'scan':
        return UITextConstants.addContactConfirmSourceScan;
      case 'phone':
        return UITextConstants.addContactConfirmSourcePhone;
      case 'search':
        return UITextConstants.addContactConfirmSourceSearch;
      case 'qr':
        return UITextConstants.addContactConfirmSourceQr;
      default:
        return '';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go(AppRoutePaths.home);
            }
          },
        ),
        middle: Text(
          UITextConstants.addContactSheetTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: FutureBuilder<_ConfirmData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return AppPageErrorState(
              semantic: UiErrorSemanticResolver.resolve(
                context,
                error: snapshot.error!,
                category: UiErrorCategory.pageLoad,
                scope: UiErrorScope.page,
              ),
              onAction: (action) async {
                if (action.type == UiErrorActionType.retry) {
                  _reload();
                }
              },
            );
          }
          if (!snapshot.hasData) {
            return const Center(child: CupertinoActivityIndicator());
          }
          return _buildBody(context, snapshot.data!);
        },
      ),
    );
  }

  Widget _buildBody(BuildContext context, _ConfirmData data) {
    final profile = data.profile;
    final addState =
        _localAddState ??
        ContactCandidateVm.addStateFromCapability(
          relationState: data.capability.relationState,
          canFollow: data.capability.canFollow,
          canUnfollow: data.capability.canUnfollow,
        );
    final handle = profile.userHandle.isNotEmpty
        ? profile.userHandle
        : widget.handle;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            SizedBox(height: AppSpacing.containerLg),
            Center(
              child: _Avatar(url: profile.avatarUrl, name: profile.displayName),
            ),
            SizedBox(height: AppSpacing.containerMd),
            Text(
              profile.displayName,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            if (handle.isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                '${UITextConstants.editProfileQuwoquanIdLabel}: $handle',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ],
            if (_sourceLabel.isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                _sourceLabel,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosTertiaryLabel(context),
                ),
              ),
            ],
            const Spacer(),
            _PrimaryButton(
              addState: addState,
              pending: _adding,
              onAdd: () => _add(addState),
            ),
            SizedBox(height: AppSpacing.containerMd),
          ],
        ),
      ),
    );
  }
}

class _ConfirmData {
  const _ConfirmData({required this.profile, required this.capability});

  final SubAccountProfileViewData profile;
  final RelationshipCapabilityDto capability;
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.url, required this.name});

  final String url;
  final String name;

  @override
  Widget build(BuildContext context) {
    final initial = name.trim().isNotEmpty
        ? name.trim().characters.first.toUpperCase()
        : '';
    final fallback = ColoredBox(
      color: AppColors.iosAccent(context).withValues(alpha: 0.12),
      child: Center(
        child: initial.isEmpty
            ? Icon(
                CupertinoIcons.person_fill,
                size: AppSpacing.iconLarge,
                color: AppColors.iosAccent(context),
              )
            : Text(
                initial,
                style: TextStyle(
                  fontSize: AppTypography.iosTitle2,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosAccent(context),
                ),
              ),
      ),
    );
    return ClipOval(
      child: SizedBox(
        width: AppSpacing.avatarUserXl,
        height: AppSpacing.avatarUserXl,
        child: url.trim().isEmpty
            ? fallback
            : AppMediaImage(
                imageSource: url,
                fit: BoxFit.cover,
                width: AppSpacing.avatarUserXl,
                height: AppSpacing.avatarUserXl,
                placeholder: fallback,
                errorWidget: fallback,
              ),
      ),
    );
  }
}

class _PrimaryButton extends StatelessWidget {
  const _PrimaryButton({
    required this.addState,
    required this.pending,
    required this.onAdd,
  });

  final ContactAddState addState;
  final bool pending;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final isAdded = addState == ContactAddState.added;
    final isSelf = addState == ContactAddState.isSelf;
    final label = switch (addState) {
      ContactAddState.added => UITextConstants.contactAlreadyAdded,
      ContactAddState.canFollowBack => UITextConstants.contactAddBack,
      ContactAddState.isSelf => UITextConstants.contactAlreadyAdded,
      _ => UITextConstants.addContactSheetTitle,
    };
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
        color: (isAdded || isSelf)
            ? AppColors.iosSeparator(context)
            : AppColors.iosAccent(context),
        onPressed: (isAdded || isSelf || pending) ? null : onAdd,
        child: pending
            ? const CupertinoActivityIndicator()
            : Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.semiBold,
                  color: (isAdded || isSelf)
                      ? AppColors.iosSecondaryLabel(context)
                      : AppColors.white,
                ),
              ),
      ),
    );
  }
}
