import 'content_operation_contracts.g.dart';

abstract interface class ContentPostPublicationWriter {
  Future<PostPublicationReceipt> submitPostPublication(
    SubmitContentPostPublicationCommand command,
  );
}
