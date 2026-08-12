import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/app_log_redactor.dart';

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
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

  test('对象字段策略在 App 日志出口覆盖 allow/drop/mask/truncate/count', () {
    final value = redactor.redactMap(<String, dynamic>{
      'location': <String, dynamic>{
        'provinceName': '四川',
        'cityName': '成都',
        'detail': '精确门牌',
        'latitude': 30.1,
      },
      'title': List<String>.filled(101, '甲').join(),
      'embedding': <double>[0.1, 0.2],
      'mediaUrls': <String>['https://a.example', 'https://b.example'],
      'tagRefs': <String>['travel.photography'],
      'moderationStatus': 'approved',
    }, operationId: 'content.post.GetPost');

    expect(value['location'], <String, dynamic>{
      'provinceName': '四川',
      'cityName': '成都',
    });
    expect(value['title'], '${List<String>.filled(100, '甲').join()}…');
    expect(value, isNot(contains('embedding')));
    expect(value['mediaUrls'], 2);
    expect(value['tagRefs'], <String>['travel.photography']);
    expect(value, isNot(contains('moderationStatus')));
  });

  test('字段长度上限与 audience 在 App 侧 fail-closed', () {
    final short = redactor.redactMap(<String, dynamic>{
      'bio': List<String>.filled(100, '乙').join(),
    }, operationId: 'user.user_account.GetUserProfile');
    final long = redactor.redactMap(<String, dynamic>{
      'bio': List<String>.filled(101, '乙').join(),
      'birthDate': '2000-01-01',
    }, operationId: 'user.user_account.GetUserProfile');

    expect(short['bio'], hasLength(100));
    expect(long, isNot(contains('bio')));
    expect(long, isNot(contains('birthDate')));
  });
}
