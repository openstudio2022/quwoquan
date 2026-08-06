// spec_ref: specs/feature-tree/product-ops-growth/outbound-share-distribution/share-attribution-and-token/spec.md#gwt-003
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/outbound_share_fact/application/public/content_outbound_share_appender.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/outbound_share_fact/outbound_share_writer_typed_double.dart';

CreateContentOutboundShareCommand _command(String referralId) =>
    CreateContentOutboundShareCommand(
      postId: 'post-outbound-share-contract',
      channel: OutboundShareChannel.systemShare,
      destinationKind: OutboundShareDestinationKind.externalApp,
      destination: 'system-share-sheet',
      referralId: referralId,
      providerReceiptId: 'receipt-$referralId',
      clientConfirmedAt: DateTime.utc(2026, 8, 5, 8),
    );

void main() {
  test('公开 appender 以 referralId 幂等记录确认后的分享事实', () async {
    final ContentOutboundShareAppender appender =
        ContentOutboundShareWriterTypedDouble();

    final first = await appender.appendOutboundShare(_command('referral-1'));
    final replay = await appender.appendOutboundShare(_command('referral-1'));
    final next = await appender.appendOutboundShare(_command('referral-2'));

    expect(first.replayed, isFalse);
    expect(replay.replayed, isTrue);
    expect(replay.eventId, first.eventId);
    expect(next.eventId, isNot(first.eventId));
    expect(next.referralId, 'referral-2');
  });
}
