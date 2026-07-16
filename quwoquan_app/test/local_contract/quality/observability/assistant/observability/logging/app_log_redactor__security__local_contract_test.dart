import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_redactor.dart';

void main() {
  const redactor = AppLogRedactor();

  test('敏感 header、JSON 字段与 presigned query 不进入日志', () {
    final value = redactor.redactText(
      'Authorization: Bearer secret.jwt.value '
      'url=https://upload.example/path?X-Amz-Signature=signature-value'
      '&access_token=access-value '
      'payload={"authCode":"oauth-code","token":"token-value"}',
    );

    expect(value, contains('Bearer ***'));
    expect(value, contains('X-Amz-Signature=***'));
    expect(value, contains('access_token=***'));
    expect(value, contains('"authCode":"***'));
    expect(value, contains('"token":"***'));
    expect(value, isNot(contains('signature-value')));
    expect(value, isNot(contains('oauth-code')));
    expect(value, isNot(contains('token-value')));
  });
}
