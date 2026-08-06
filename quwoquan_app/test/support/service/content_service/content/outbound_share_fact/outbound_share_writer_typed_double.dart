import 'package:quwoquan_app/service/content_service/content/outbound_share_fact/application/public/content_outbound_share_appender.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class ContentOutboundShareWriterTypedDouble
    implements ContentOutboundShareAppender {
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
      eventId: 'outbound_share_fact_${_receiptByReferral.length + 1}',
      postId: command.postId,
      channel: command.channel,
      referralId: command.referralId,
      occurredAt: command.clientConfirmedAt,
      replayed: false,
    );
    _receiptByReferral[command.referralId] = result;
    return result;
  }
}
