import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

class SocialAuthorizationRequest {
  const SocialAuthorizationRequest({
    required this.payload,
    required this.expiresAt,
  });

  factory SocialAuthorizationRequest.fromMap(Map<String, dynamic> map) {
    return SocialAuthorizationRequest(
      payload: map['authorizationPayload']?.toString().trim() ?? '',
      expiresAt:
          DateTime.tryParse(map['expiresAt']?.toString() ?? '') ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    );
  }

  final String payload;
  final DateTime expiresAt;

  bool get isUsable =>
      payload.isNotEmpty && expiresAt.isAfter(DateTime.now().toUtc());
}

abstract interface class SocialAuthorizationRepository {
  Future<SocialAuthorizationRequest> createAlipayAuthorizationRequest();
}

class RemoteSocialAuthorizationRepository
    implements SocialAuthorizationRepository {
  RemoteSocialAuthorizationRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
  }) : _client = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _client;
  final String _baseUrl;

  @override
  Future<SocialAuthorizationRequest> createAlipayAuthorizationRequest() async {
    const operationId =
        UserApiMetadata.createAlipayAuthorizationRequestOperation;
    const surfaceId = UserRequestPageIds.createAlipayAuthorizationRequest;
    final response = await _client.postJson(
      Uri.parse(
        '$_baseUrl${UserApiMetadata.createAlipayAuthorizationRequestPath}',
      ),
      headers: CloudRequestHeaders.forSurfaceOperation(
        surfaceId: surfaceId,
        operationId: operationId,
        clientPageId: surfaceId,
      ),
      body: <String, dynamic>{
        'platform': CloudRequestHeaders.platform(),
        'appVersion': CloudRequestHeaders.appVersion,
      },
    );
    final request = SocialAuthorizationRequest.fromMap(
      CloudResponseDecoder.asObject(response, context: surfaceId),
    );
    if (!request.isUsable) {
      throw StateError('alipay authorization payload unavailable');
    }
    return request;
  }
}
