import 'content_operation_contracts.g.dart';

abstract interface class ContentOutboundShareAppendWriter {
  Future<OutboundShareFactResult> appendOutboundShare(
    CreateContentOutboundShareCommand command,
  );
}
