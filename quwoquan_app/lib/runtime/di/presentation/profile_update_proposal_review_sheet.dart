import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show profileEditProposalCommandWriterProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class ProfileUpdateProposalReviewSheet extends ConsumerStatefulWidget {
  const ProfileUpdateProposalReviewSheet({super.key, required this.proposal});

  final ProfileUpdateProposalView proposal;

  @override
  ConsumerState<ProfileUpdateProposalReviewSheet> createState() =>
      _ProfileUpdateProposalReviewSheetState();
}

final class _ProfileUpdateProposalReviewSheetState
    extends ConsumerState<ProfileUpdateProposalReviewSheet> {
  bool _busy = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _track('expose', result: widget.proposal.status.wireName);
    });
  }

  void _track(String action, {String? result, String? failReasonCode}) {
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'profile_update_proposal',
            action: action,
            pageName: 'ProfileUpdateProposalReviewSheet',
            targetType: 'profile_update_proposal',
            targetKey: widget.proposal.id,
            payload: <String, dynamic>{
              'result': ?result,
              'failReasonCode': ?failReasonCode,
            },
          ),
    );
  }

  Future<void> _approve() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _errorMessage = null;
    });
    try {
      final writer = ref.read(profileEditProposalCommandWriterProvider);
      if (widget.proposal.status == ProposalStatus.pending) {
        await writer.confirm(
          ConfirmProfileUpdateProposalCommand(proposalId: widget.proposal.id),
        );
      }
      if (widget.proposal.status == ProposalStatus.pending ||
          widget.proposal.status == ProposalStatus.confirmed ||
          widget.proposal.status == ProposalStatus.applying) {
        await writer.apply(
          ApplyProfileUpdateProposalCommand(proposalId: widget.proposal.id),
        );
      }
      if (!mounted) return;
      _track('apply', result: 'succeeded');
      AppToast.show(context, ProfileText.editProfileProposalApplied);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) return;
      final semantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.dialog,
      );
      setState(() {
        _busy = false;
        _errorMessage = semantic.message;
      });
      _track('apply', result: 'failed', failReasonCode: semantic.sourceCode);
    }
  }

  Future<void> _reject() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _errorMessage = null;
    });
    try {
      await ref
          .read(profileEditProposalCommandWriterProvider)
          .reject(
            RejectProfileUpdateProposalCommand(proposalId: widget.proposal.id),
          );
      if (!mounted) return;
      _track('reject', result: 'succeeded');
      AppToast.show(context, ProfileText.editProfileProposalRejected);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) return;
      final semantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.dialog,
      );
      setState(() {
        _busy = false;
        _errorMessage = semantic.message;
      });
      _track('reject', result: 'failed', failReasonCode: semantic.sourceCode);
    }
  }

  Future<void> _rollback() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _errorMessage = null;
    });
    try {
      await ref
          .read(profileEditProposalCommandWriterProvider)
          .rollback(
            RollbackProfileUpdateProposalCommand(
              proposalId: widget.proposal.id,
            ),
          );
      if (!mounted) return;
      _track('rollback', result: 'succeeded');
      AppToast.show(context, ProfileText.editProfileProposalRolledBack);
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) return;
      final semantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.dialog,
      );
      setState(() {
        _busy = false;
        _errorMessage = semantic.message;
      });
      _track('rollback', result: 'failed', failReasonCode: semantic.sourceCode);
    }
  }

  @override
  Widget build(BuildContext context) {
    final changes = _changeRows(widget.proposal);
    final reviewBasis = _reviewBasisRows(widget.proposal);
    final canApprove =
        widget.proposal.status == ProposalStatus.pending ||
        widget.proposal.status == ProposalStatus.confirmed ||
        widget.proposal.status == ProposalStatus.applying;
    final canReject =
        widget.proposal.status == ProposalStatus.pending ||
        widget.proposal.status == ProposalStatus.confirmed;
    final canRollback = widget.proposal.status == ProposalStatus.applied;
    return AppBottomModalSurface(
      panelKey: const ValueKey<String>('profile-proposal-review-sheet'),
      onDismiss: _busy ? () {} : () => Navigator.of(context).pop(false),
      maxHeightRatio: 0.86,
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Flexible(
              fit: FlexFit.loose,
              child: ListView(
                shrinkWrap: true,
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  0,
                  AppSpacing.containerMd,
                  AppSpacing.containerSm,
                ),
                children: <Widget>[
                  Text(
                    ProfileText.editProfileProposalTitle,
                    style: TextStyle(
                      fontSize: AppTypography.iosTitle2,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  Text(
                    _sourceLabel(widget.proposal.source),
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.interGroupMd),
                  Text(
                    ProfileText.editProfileProposalReviewBasis,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: FontWeight.w600,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  ProfileIosGroupedSection(
                    showDividers: true,
                    children: reviewBasis,
                  ),
                  SizedBox(height: AppSpacing.interGroupMd),
                  Text(
                    ProfileText.editProfileProposalChanges,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: FontWeight.w600,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  ProfileIosGroupedSection(
                    showDividers: true,
                    children: changes,
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                0,
                AppSpacing.containerMd,
                AppSpacing.containerMd,
              ),
              child: Column(
                children: <Widget>[
                  if (_errorMessage != null) ...<Widget>[
                    AppFormErrorCard(
                      key: const ValueKey<String>('profile-proposal-error'),
                      density: AppFormErrorCardDensity.compact,
                      semantic: UiErrorSemantic(
                        category: UiErrorCategory.submit,
                        scope: UiErrorScope.dialog,
                        title: '',
                        message: _errorMessage!,
                        presentation: UiErrorPresentation.formInlineCard,
                      ),
                    ),
                    SizedBox(height: AppSpacing.containerSm),
                  ],
                  if (canApprove) ...<Widget>[
                    ProfileIosActionButton(
                      key: const ValueKey<String>('profile-proposal-approve'),
                      label: widget.proposal.status == ProposalStatus.applying
                          ? ProfileText.editProfileProposalResumeApply
                          : ProfileText.editProfileProposalApprove,
                      style: ProfileIosActionStyle.filled,
                      onPressed: _busy ? null : _approve,
                    ),
                    if (canReject) ...<Widget>[
                      SizedBox(height: AppSpacing.containerSm),
                      ProfileIosActionButton(
                        key: const ValueKey<String>('profile-proposal-reject'),
                        label: ProfileText.editProfileProposalReject,
                        style: ProfileIosActionStyle.outlined,
                        onPressed: _busy ? null : _reject,
                      ),
                    ],
                  ],
                  if (canRollback)
                    ProfileIosActionButton(
                      key: const ValueKey<String>('profile-proposal-rollback'),
                      label: ProfileText.editProfileProposalRollback,
                      style: ProfileIosActionStyle.outlined,
                      onPressed: _busy ? null : _rollback,
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

List<Widget> _reviewBasisRows(ProfileUpdateProposalView proposal) {
  return <Widget>[
    ProfileIosGroupedCell(
      title: ProfileText.editProfileProposalReason,
      subtitle: proposal.reason,
      showChevron: false,
    ),
    ProfileIosGroupedCell(
      title: ProfileText.editProfileProposalEvidence,
      subtitle: proposal.evidenceRefs.join('\n'),
      showChevron: false,
    ),
    ProfileIosGroupedCell(
      title: ProfileText.editProfileProposalImpactScope,
      subtitle: proposal.impactScope.map(_profileChangeFieldLabel).join(', '),
      showChevron: false,
    ),
  ];
}

List<Widget> _changeRows(ProfileUpdateProposalView changes) {
  final rows = <Widget>[];
  void add(String label, Object? value, {bool allowEmpty = false}) {
    if (value == null) return;
    final text = value is bool ? (value ? '是' : '否') : value.toString().trim();
    rows.add(
      ProfileIosGroupedCell(
        title: label,
        showChevron: false,
        trailing: Text(
          text.isEmpty && allowEmpty
              ? ProfileText.editProfileProposalEmptyValue
              : text,
        ),
      ),
    );
  }

  add(ProfileText.editProfileNicknameLabel, changes.displayName);
  add(ProfileText.editProfileBioLabel, changes.bio, allowEmpty: true);
  add(ProfileText.editProfileAvatarLabel, changes.avatarMediaAssetId);
  add(ProfileText.editProfileCoverLabel, changes.backgroundMediaAssetId);
  add(ProfileText.editProfileProposalPrivateField, changes.isPrivate);
  add(ProfileText.editProfileProposalIsolationField, changes.isolationLevel);
  add(ProfileText.editProfileProposalPurposeField, changes.purposeHint);
  return rows;
}

String _profileChangeFieldLabel(String field) => switch (field) {
  'displayName' => ProfileText.editProfileNicknameLabel,
  'bio' => ProfileText.editProfileBioLabel,
  'avatarMediaAssetId' => ProfileText.editProfileAvatarLabel,
  'backgroundMediaAssetId' => ProfileText.editProfileCoverLabel,
  'isPrivate' => ProfileText.editProfileProposalPrivateField,
  'isolationLevel' => ProfileText.editProfileProposalIsolationField,
  'purposeHint' => ProfileText.editProfileProposalPurposeField,
  _ => ProfileText.editProfileProposalImpactScope,
};

String _sourceLabel(ProposalSource source) => switch (source) {
  ProposalSource.assistant => ProfileText.editProfileProposalSourceAssistant,
  ProposalSource.external => ProfileText.editProfileProposalSourceExternal,
  ProposalSource.persona => ProfileText.editProfileProposalSourcePersona,
};
