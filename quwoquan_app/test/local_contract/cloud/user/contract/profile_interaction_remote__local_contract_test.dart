import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';

void main() {
  RemoteUserProfileRepository repositoryReturning(http.Response response) {
    return RemoteUserProfileRepository(
      httpClient: CloudHttpClient(client: MockClient((_) async => response)),
      baseUrl: 'https://gateway.example.test',
    );
  }

  test('ProfileInteraction Remote 对 404 fail-closed，不回退空列表', () async {
    final repository = repositoryReturning(
      http.Response(
        jsonEncode(<String, Object?>{
          'code': 'CONTENT.USER.interaction_not_found',
          'message': 'interaction not found',
        }),
        404,
      ),
    );

    await expectLater(
      repository.listUserInteractionReceived('persona-1'),
      throwsA(
        isA<CloudException>().having(
          (error) => error.statusCode,
          'statusCode',
          404,
        ),
      ),
    );
  });

  test('ProfileInteraction Remote 只把 200 page 解码为空结果', () async {
    final repository = repositoryReturning(
      http.Response(
        jsonEncode(<String, Object?>{
          'items': <Object?>[],
          'nextCursor': '',
          'hasMore': false,
        }),
        200,
      ),
    );

    expect(await repository.listUserInteractionSent('persona-1'), isEmpty);
  });
}
