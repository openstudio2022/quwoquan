import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'observability/recording_cloud_operation_telemetry_sink.dart';

const remoteApiPathTestBaseUrl = 'https://test-gateway.example.com';

typedef CapturedRemoteApiPathRequest = ({
  String method,
  String path,
  Map<String, String> query,
  Map<String, String> headers,
  Map<String, dynamic> body,
});

typedef RemoteApiPathResponseFactory =
    FutureOr<http.Response> Function(http.Request request);

CloudOperationContract canonicalRemoteApiOperation(String operationId) {
  final operation = appCloudOperationContracts[operationId];
  if (operation == null) {
    throw StateError('Unknown canonical App operation: $operationId');
  }
  return operation;
}

String canonicalRemoteApiPath(
  String operationId, {
  Map<String, String> pathParameters = const <String, String>{},
}) {
  final operation = canonicalRemoteApiOperation(operationId);
  return renderRemoteApiPathContractShapeForTest(
    operationId: operationId,
    pathTemplate: operation.pathTemplate,
    requestPathBindings: operation.requestPathBindings,
    pathParameters: pathParameters,
  );
}

/// Renders the same fail-closed path contract from an explicit shape so the
/// harness can prove malformed generated shapes are rejected as well.
String renderRemoteApiPathContractShapeForTest({
  required String operationId,
  required String pathTemplate,
  required List<CloudOperationRequestBinding> requestPathBindings,
  Map<String, String> pathParameters = const <String, String>{},
}) {
  final template = pathTemplate;
  if (!template.startsWith('/') ||
      template.contains('?') ||
      template.contains('#') ||
      template.contains('//') ||
      (template.length > 1 && template.endsWith('/'))) {
    throw StateError(
      '$operationId has an invalid canonical path template: $template',
    );
  }

  final placeholderPattern = RegExp(r'\{([^{}]+)\}');
  final placeholderMatches = placeholderPattern.allMatches(template).toList();
  final placeholderNamePattern = RegExp(r'^[A-Za-z][A-Za-z0-9_]*$');
  final placeholderNamesInOrder = placeholderMatches
      .map((match) => match.group(1)!)
      .toList(growable: false);
  final templateWithoutPlaceholders = template.replaceAll(
    placeholderPattern,
    '',
  );
  if (templateWithoutPlaceholders.contains('{') ||
      templateWithoutPlaceholders.contains('}') ||
      placeholderNamesInOrder.any(
        (name) => !placeholderNamePattern.hasMatch(name),
      )) {
    throw StateError(
      '$operationId has malformed canonical path placeholders: $template',
    );
  }
  final placeholderNames = placeholderNamesInOrder.toSet();
  if (placeholderNames.length != placeholderNamesInOrder.length) {
    throw StateError('$operationId has duplicate path placeholders');
  }

  final bindingNamesInOrder = requestPathBindings
      .map((binding) => binding.name)
      .toList(growable: false);
  final bindingFieldsInOrder = requestPathBindings
      .map((binding) => binding.field)
      .toList(growable: false);
  final bindingNames = bindingNamesInOrder.toSet();
  final bindingFields = bindingFieldsInOrder.toSet();
  if (requestPathBindings.any(
        (binding) =>
            !binding.required ||
            binding.name.isEmpty ||
            binding.name.trim() != binding.name ||
            !placeholderNamePattern.hasMatch(binding.name) ||
            binding.field.isEmpty ||
            binding.field.trim() != binding.field,
      ) ||
      bindingNames.length != bindingNamesInOrder.length ||
      bindingFields.length != bindingFieldsInOrder.length) {
    throw StateError('$operationId has invalid or duplicate path bindings');
  }
  if (bindingNames.length != placeholderNames.length ||
      !bindingNames.containsAll(placeholderNames)) {
    throw StateError(
      '$operationId path bindings do not match its template placeholders',
    );
  }
  final providedNames = pathParameters.keys.toSet();
  if (providedNames.length != placeholderNames.length ||
      !providedNames.containsAll(placeholderNames)) {
    final missing = placeholderNames.difference(providedNames).toList()..sort();
    final unexpected = providedNames.difference(placeholderNames).toList()
      ..sort();
    throw StateError(
      '$operationId path parameter cardinality mismatch; '
      'missing=$missing unexpected=$unexpected',
    );
  }

  final resolvedSegments = template
      .split('/')
      .skip(1)
      .map((segment) {
        return segment.replaceAllMapped(placeholderPattern, (match) {
          final name = match.group(1)!;
          final value = pathParameters[name] ?? '';
          if (value.isEmpty || value.trim() != value) {
            throw StateError(
              '$operationId has an empty or padded path parameter: $name',
            );
          }
          return value;
        });
      })
      .toList(growable: false);

  // Raw parameter values become URI path segments exactly once. A value such
  // as `message/a` therefore becomes `message%2Fa`, never a second path level.
  return resolvedSegments.isEmpty
      ? '/'
      : '/${Uri(pathSegments: resolvedSegments).path}';
}

MockClient captureRemoteApiPathClient(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
}) {
  return MockClient((request) async {
    final decodedRequestBody = request.body.isEmpty
        ? const <String, dynamic>{}
        : jsonDecode(request.body);
    log.add((
      method: request.method,
      path: request.url.path,
      query: request.url.queryParameters,
      headers: Map<String, String>.from(request.headers),
      body: decodedRequestBody is Map
          ? Map<String, dynamic>.from(decodedRequestBody)
          : const <String, dynamic>{},
    ));
    return responseFor(request);
  });
}

http.Response remoteApiPathJsonResponse(Object body, {int statusCode = 200}) {
  return http.Response(
    body is String ? body : json.encode(body),
    statusCode,
    headers: const {'content-type': 'application/json'},
  );
}

GeneratedCloudOperationClient buildRemoteApiPathOperationClient(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
  bool authenticated = true,
}) {
  return buildGeneratedCloudOperationClient(
    httpClient: buildRemoteApiPathHttpClient(
      log,
      responseFor: responseFor,
      authenticated: authenticated,
    ),
    clientContextProvider: const RemoteApiPathTestCloudClientContext(),
    telemetrySink: RecordingCloudOperationTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse(remoteApiPathTestBaseUrl),
    ),
  );
}

CloudHttpClient buildRemoteApiPathHttpClient(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
  bool authenticated = true,
}) {
  return CloudHttpClient(
    client: captureRemoteApiPathClient(log, responseFor: responseFor),
    authTokenProvider: authenticated
        ? const RemoteApiPathTestAuthTokenProvider()
        : null,
  );
}

final class RemoteApiPathTestCloudClientContext
    implements CloudClientContextProvider {
  const RemoteApiPathTestCloudClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'integration-contract-session',
      deviceActorId: 'integration-contract-device',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class RemoteApiPathTestAuthTokenProvider
    implements CloudAuthTokenProvider {
  const RemoteApiPathTestAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'integration-contract-token';
}

void expectRemoteApiPathHeaders(
  Map<String, String> headers, {
  required String clientPageId,
  required String surfaceId,
  required String operationId,
}) {
  expect(headers['X-Client-Page-Id'], clientPageId);
  expect(headers['X-Client-Surface-Id'], surfaceId);
  expect(headers['X-Client-Operation-Id'], operationId);
  expect(headers['X-Trace-Id'], contains(surfaceId));
  expect(headers['X-Trace-Id'], contains(operationId));
  expect(headers['X-Request-Id'], contains(surfaceId));
  expect(headers['X-Request-Id'], contains(operationId));
}
