/// Encoded wire components produced by an operation-specific request encoder.
///
/// Business callers never construct this type. Generated typed clients use it
/// to keep transport path/query/body details outside business Facet methods.
final class CloudOperationRequestPayload {
  const CloudOperationRequestPayload({
    this.pathParameters = const <String, String>{},
    this.queryParameters = const <String, String>{},
    this.headers = const <String, String>{},
    this.body,
  });

  final Map<String, String> pathParameters;
  final Map<String, String> queryParameters;

  /// Operation-specific conditional headers such as `If-Match`.
  ///
  /// Authentication, actor, idempotency, trace and surface headers are runtime
  /// context and therefore cannot be supplied through this payload.
  final Map<String, String> headers;
  final Object? body;
}
