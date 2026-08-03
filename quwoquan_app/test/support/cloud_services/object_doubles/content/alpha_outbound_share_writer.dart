import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class AlphaContentOutboundShareWriter
    implements ContentOutboundShareAppendWriter {
  final Map<String, OutboundShareFactResult> _receiptByReferral =
      <String, OutboundShareFactResult>{};

  @override
  Future<OutboundShareFactResult> appendOutboundShare(
    CreateContentOutboundShareCommand command,
  ) async {
    final existing = _receiptByReferral[command.referralId];
    if (existing != null) {
      return OutboundShareFactResult(
        eventId: existing.eventId,
        postId: existing.postId,
        channel: existing.channel,
        referralId: existing.referralId,
        occurredAt: existing.occurredAt,
        replayed: true,
      );
    }
    final result = OutboundShareFactResult(
      eventId: 'alpha_outbound_share_${_receiptByReferral.length + 1}',
      postId: command.postId,
      channel: command.channel.wireValue,
      referralId: command.referralId,
      occurredAt: command.clientConfirmedAt,
      replayed: false,
    );
    _receiptByReferral[command.referralId] = result;
    return result;
  }
}
