import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
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
      _track('expose', result: widget.proposal.status.name);
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
      if (widget.proposal.status == ProfileUpdateProposalStatus.pending) {
        await writer.confirm(
          ConfirmProfileUpdateProposalCommand(proposalId: widget.proposal.id),
        );
      }
      if (widget.proposal.status == ProfileUpdateProposalStatus.pending ||
          widget.proposal.status == ProfileUpdateProposalStatus.confirmed ||
          widget.proposal.status == ProfileUpdateProposalStatus.applying) {
        await writer.apply(
          ApplyProfileUpdateProposalCommand(proposalId: widget.proposal.id),
        );
      }
      if (!mounted) return;
      _track('apply', result: 'succeeded');
      AppToast.show(context, UITextConstants.editProfileProposalApplied);
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
      AppToast.show(context, UITextConstants.editProfileProposalRejected);
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
      AppToast.show(context, UITextConstants.editProfileProposalRolledBack);
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
    final changes = _changeRows(widget.proposal.changes);
    final reviewBasis = _reviewBasisRows(widget.proposal);
    final canApprove =
        widget.proposal.status == ProfileUpdateProposalStatus.pending ||
        widget.proposal.status == ProfileUpdateProposalStatus.confirmed ||
        widget.proposal.status == ProfileUpdateProposalStatus.applying;
    final canReject =
        widget.proposal.status == ProfileUpdateProposalStatus.pending ||
        widget.proposal.status == ProfileUpdateProposalStatus.confirmed;
    final canRollback =
        widget.proposal.status == ProfileUpdateProposalStatus.applied;
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
                    UITextConstants.editProfileProposalTitle,
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
                    UITextConstants.editProfileProposalReviewBasis,
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
                    UITextConstants.editProfileProposalChanges,
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
                      label:
                          widget.proposal.status ==
                              ProfileUpdateProposalStatus.applying
                          ? UITextConstants.editProfileProposalResumeApply
                          : UITextConstants.editProfileProposalApprove,
                      style: ProfileIosActionStyle.filled,
                      onPressed: _busy ? null : _approve,
                    ),
                    if (canReject) ...<Widget>[
                      SizedBox(height: AppSpacing.containerSm),
                      ProfileIosActionButton(
                        key: const ValueKey<String>('profile-proposal-reject'),
                        label: UITextConstants.editProfileProposalReject,
                        style: ProfileIosActionStyle.outlined,
                        onPressed: _busy ? null : _reject,
                      ),
                    ],
                  ],
                  if (canRollback)
                    ProfileIosActionButton(
                      key: const ValueKey<String>('profile-proposal-rollback'),
                      label: UITextConstants.editProfileProposalRollback,
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
      title: UITextConstants.editProfileProposalReason,
      subtitle: proposal.reason,
      showChevron: false,
    ),
    ProfileIosGroupedCell(
      title: UITextConstants.editProfileProposalEvidence,
      subtitle: proposal.evidenceRefs.join('\n'),
      showChevron: false,
    ),
    ProfileIosGroupedCell(
      title: UITextConstants.editProfileProposalImpactScope,
      subtitle: proposal.impactScope.map(_profileChangeFieldLabel).join(', '),
      showChevron: false,
    ),
  ];
}

List<Widget> _changeRows(ProfileChangeSet changes) {
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
              ? UITextConstants.editProfileProposalEmptyValue
              : text,
        ),
      ),
    );
  }

  add(UITextConstants.editProfileNicknameLabel, changes.displayName);
  add(UITextConstants.editProfileBioLabel, changes.bio, allowEmpty: true);
  add(UITextConstants.editProfileAvatarLabel, changes.avatarMediaAssetId);
  add(UITextConstants.editProfileCoverLabel, changes.backgroundMediaAssetId);
  add(UITextConstants.editProfileProposalPrivateField, changes.isPrivate);
  add(
    UITextConstants.editProfileProposalIsolationField,
    changes.isolationLevel,
  );
  add(UITextConstants.editProfileProposalPurposeField, changes.purposeHint);
  return rows;
}

String _profileChangeFieldLabel(String field) => switch (field) {
  'displayName' => UITextConstants.editProfileNicknameLabel,
  'bio' => UITextConstants.editProfileBioLabel,
  'avatarMediaAssetId' => UITextConstants.editProfileAvatarLabel,
  'backgroundMediaAssetId' => UITextConstants.editProfileCoverLabel,
  'isPrivate' => UITextConstants.editProfileProposalPrivateField,
  'isolationLevel' => UITextConstants.editProfileProposalIsolationField,
  'purposeHint' => UITextConstants.editProfileProposalPurposeField,
  _ => UITextConstants.editProfileProposalImpactScope,
};

String _sourceLabel(ProfileUpdateProposalSource source) => switch (source) {
  ProfileUpdateProposalSource.assistant =>
    UITextConstants.editProfileProposalSourceAssistant,
  ProfileUpdateProposalSource.external =>
    UITextConstants.editProfileProposalSourceExternal,
  ProfileUpdateProposalSource.persona =>
    UITextConstants.editProfileProposalSourcePersona,
};
