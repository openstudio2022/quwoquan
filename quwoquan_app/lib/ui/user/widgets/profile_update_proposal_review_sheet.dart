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

  Future<void> _approve() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _errorMessage = null;
    });
    try {
      final writer = ref.read(profileEditProposalCommandWriterProvider);
      var version = widget.proposal.version;
      if (widget.proposal.status == ProfileUpdateProposalStatus.pending) {
        final confirmed = await writer.confirm(
          ConfirmProfileUpdateProposalCommand(
            proposalId: widget.proposal.id,
            expectedProposalVersion: version,
          ),
        );
        version = confirmed.version;
      }
      if (widget.proposal.status == ProfileUpdateProposalStatus.pending ||
          widget.proposal.status == ProfileUpdateProposalStatus.confirmed) {
        await writer.apply(
          ApplyProfileUpdateProposalCommand(
            proposalId: widget.proposal.id,
            expectedProposalVersion: version,
          ),
        );
      }
      if (!mounted) return;
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
            RejectProfileUpdateProposalCommand(
              proposalId: widget.proposal.id,
              expectedProposalVersion: widget.proposal.version,
            ),
          );
      if (!mounted) return;
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
    }
  }

  @override
  Widget build(BuildContext context) {
    final changes = _changeRows(widget.proposal.changes);
    final actionable =
        widget.proposal.status == ProfileUpdateProposalStatus.pending ||
        widget.proposal.status == ProfileUpdateProposalStatus.confirmed;
    return AppBottomModalSurface(
      panelKey: const ValueKey<String>('profile-proposal-review-sheet'),
      onDismiss: _busy ? () {} : () => Navigator.of(context).pop(false),
      maxHeightRatio: 0.86,
      child: SafeArea(
        top: false,
        child: ListView(
          shrinkWrap: true,
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            0,
            AppSpacing.containerMd,
            AppSpacing.containerMd,
          ),
          children: <Widget>[
            Text(
              UITextConstants.editProfileProposalTitle,
              style: TextStyle(
                fontSize: AppTypography.iosTitle2,
                fontWeight: FontWeight.w600,
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
              UITextConstants.editProfileProposalChanges,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                fontWeight: FontWeight.w600,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            ProfileIosGroupedSection(showDividers: true, children: changes),
            if (_errorMessage != null) ...<Widget>[
              SizedBox(height: AppSpacing.containerSm),
              Text(
                _errorMessage!,
                key: const ValueKey<String>('profile-proposal-error'),
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosDestructive(context),
                ),
              ),
            ],
            if (actionable) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupMd),
              ProfileIosActionButton(
                key: const ValueKey<String>('profile-proposal-approve'),
                label: UITextConstants.editProfileProposalApprove,
                style: ProfileIosActionStyle.filled,
                onPressed: _busy ? null : _approve,
              ),
              SizedBox(height: AppSpacing.containerSm),
              ProfileIosActionButton(
                key: const ValueKey<String>('profile-proposal-reject'),
                label: UITextConstants.editProfileProposalReject,
                style: ProfileIosActionStyle.outlined,
                onPressed: _busy ? null : _reject,
              ),
            ],
          ],
        ),
      ),
    );
  }
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
  add('私密资料', changes.isPrivate);
  add('资料隔离级别', changes.isolationLevel);
  add('用途说明', changes.purposeHint);
  return rows;
}

String _sourceLabel(ProfileUpdateProposalSource source) => switch (source) {
  ProfileUpdateProposalSource.assistant => '来自私助的建议',
  ProfileUpdateProposalSource.external => '来自已授权外部服务的建议',
  ProfileUpdateProposalSource.persona => '来自当前身份的建议',
};
