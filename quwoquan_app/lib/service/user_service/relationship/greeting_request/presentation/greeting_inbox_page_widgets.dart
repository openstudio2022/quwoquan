part of 'greeting_inbox_page.dart';

class _GreetingRequestCard extends StatelessWidget {
  const _GreetingRequestCard({
    required this.request,
    required this.box,
    required this.isDark,
    required this.busy,
    required this.onReply,
    required this.onIgnore,
    required this.onCancel,
    required this.onOpenConversation,
  });

  final GreetingRequestViewData request;
  final _GreetingBox box;
  final bool isDark;
  final bool busy;
  final VoidCallback onReply;
  final VoidCallback onIgnore;
  final VoidCallback onCancel;
  final VoidCallback onOpenConversation;

  @override
  Widget build(BuildContext context) {
    final peerId = box == _GreetingBox.received
        ? request.requesterPersonaId
        : request.targetPersonaId;
    final message = request.requestMessage?.trim();
    final intersectionText = request.intersectionSnapshot?.primaryText.trim();
    return DecoratedBox(
      decoration: BoxDecoration(
        color: SettingsSemanticConstants.blockBackground(isDark),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    peerId.isEmpty ? ChatText.chatGreetingPeerFallback : peerId,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: AppColors.iosLabel(context),
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                ),
                _GreetingStatusChip(status: request.status),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              message == null || message.isEmpty
                  ? ChatText.chatGreetingDefaultMessage
                  : message,
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.iosSubheadline,
              ),
            ),
            if (intersectionText != null &&
                intersectionText.isNotEmpty) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                intersectionText,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: AppColors.iosLabel(context),
                  fontSize: AppTypography.iosFootnote,
                ),
              ),
            ],
            if (request.isPending) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupMd),
              if (box == _GreetingBox.received)
                Row(
                  children: <Widget>[
                    Expanded(
                      child: CupertinoButton.filled(
                        onPressed: busy ? null : onReply,
                        child: busy
                            ? AppRequestFeedback.inline()
                            : const Text(ChatText.chatGreetingInboxReply),
                      ),
                    ),
                    SizedBox(width: AppSpacing.interGroupSm),
                    CupertinoButton(
                      onPressed: busy ? null : onIgnore,
                      child: const Text(ChatText.chatGreetingInboxIgnore),
                    ),
                  ],
                )
              else
                Align(
                  alignment: Alignment.centerRight,
                  child: CupertinoButton(
                    onPressed: busy ? null : onCancel,
                    child: busy
                        ? AppRequestFeedback.inline()
                        : const Text(ChatText.chatGreetingCancel),
                  ),
                ),
            ] else if (request.isReplied &&
                (request.promotedConversationId?.isNotEmpty ??
                    false)) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupMd),
              Align(
                alignment: Alignment.centerRight,
                child: CupertinoButton(
                  onPressed: onOpenConversation,
                  child: const Text(ProfileText.profileDirectMessage),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _GreetingStatusChip extends StatelessWidget {
  const _GreetingStatusChip({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupXs,
        ),
        child: Text(
          _statusLabel,
          style: TextStyle(
            color: AppColors.iosSecondaryLabel(context),
            fontSize: AppTypography.iosCaption1,
          ),
        ),
      ),
    );
  }

  String get _statusLabel {
    return switch (status) {
      'replied' => ChatText.chatGreetingStatusReplied,
      'ignored' => ChatText.chatGreetingStatusIgnored,
      'blocked' => ChatText.chatGreetingStatusBlocked,
      'cancelled' => ChatText.chatGreetingStatusCancelled,
      'expired' => ChatText.chatGreetingStatusExpired,
      _ => ChatText.chatGreetingStatusPending,
    };
  }
}
