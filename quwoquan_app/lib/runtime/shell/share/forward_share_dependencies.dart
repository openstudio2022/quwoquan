import 'package:quwoquan_app/runtime/shell/share/forward_share_models.dart';

typedef ForwardRecentRecipientLoader =
    Future<List<AppForwardRecipient>> Function({required int limit});

typedef ForwardContactRecipientLoader =
    Future<List<AppForwardRecipient>> Function({
      required int limit,
      required bool groupsOnly,
    });

typedef ForwardCardSender =
    Future<void> Function({
      required AppForwardPayload payload,
      required AppForwardRecipient recipient,
      required String note,
      required String clientMsgId,
    });

/// Runtime-shell contract supplied by the Chat production composition.
final class ForwardShareDependencies {
  const ForwardShareDependencies({
    required this.loadRecentRecipients,
    required this.loadContactRecipients,
    required this.sendCard,
  });

  final ForwardRecentRecipientLoader loadRecentRecipients;
  final ForwardContactRecipientLoader loadContactRecipients;
  final ForwardCardSender sendCard;
}
