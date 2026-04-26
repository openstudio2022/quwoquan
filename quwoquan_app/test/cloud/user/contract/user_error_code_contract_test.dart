import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';

void main() {
  group('UserErrorCode — 常规契约', () {
    test('所有错误码存在且 code 非空', () {
      for (final e in UserErrorCode.values) {
        expect(
          e.code,
          isNotEmpty,
          reason: '${e.name} code should not be empty',
        );
        expect(
          e.defaultMessage,
          isNotEmpty,
          reason: '${e.name} defaultMessage should not be empty',
        );
        expect(
          e.httpStatus,
          greaterThan(0),
          reason: '${e.name} httpStatus should be > 0',
        );
      }
    });

    test('errors.yaml 全部 7 个错误码覆盖', () {
      expect(UserErrorCode.values.length, 7);
      expect(UserErrorCode.userNotFound.code, 'USER.USER.not_found');
      expect(UserErrorCode.unauthorized.code, 'USER.USER.unauthorized');
      expect(UserErrorCode.forbidden.code, 'USER.USER.forbidden');
      expect(UserErrorCode.nicknameTaken.code, 'USER.USER.nickname_taken');
      expect(UserErrorCode.invalidArgument.code, 'USER.USER.invalid_argument');
      expect(UserErrorCode.rateLimited.code, 'USER.USER.rate_limited');
      expect(UserErrorCode.internalError.code, 'USER.SYSTEM.internal_error');
    });

    test('fromCode 反向查找正确', () {
      expect(
        UserErrorCode.fromCode('USER.USER.not_found'),
        UserErrorCode.userNotFound,
      );
      expect(
        UserErrorCode.fromCode('USER.USER.nickname_taken'),
        UserErrorCode.nicknameTaken,
      );
      expect(
        UserErrorCode.fromCode('USER.SYSTEM.internal_error'),
        UserErrorCode.internalError,
      );
    });

    test('HTTP 状态码与 errors.yaml 一致', () {
      expect(UserErrorCode.userNotFound.httpStatus, 404);
      expect(UserErrorCode.unauthorized.httpStatus, 401);
      expect(UserErrorCode.forbidden.httpStatus, 403);
      expect(UserErrorCode.nicknameTaken.httpStatus, 409);
      expect(UserErrorCode.invalidArgument.httpStatus, 400);
      expect(UserErrorCode.rateLimited.httpStatus, 429);
      expect(UserErrorCode.internalError.httpStatus, 500);
    });
  });

  group('UserErrorCode — 兼容性契约', () {
    test('fromCode 对未知 code 返回 null', () {
      expect(UserErrorCode.fromCode('NONEXISTENT.CODE'), isNull);
      expect(UserErrorCode.fromCode(''), isNull);
    });
  });

  group('UserErrorCode — 异常/边界契约', () {
    test('defaultMessage 中文非空', () {
      expect(UserErrorCode.userNotFound.defaultMessage, '用户不存在');
      expect(UserErrorCode.unauthorized.defaultMessage, '请先登录');
      expect(UserErrorCode.nicknameTaken.defaultMessage, contains('昵称'));
      expect(UserErrorCode.rateLimited.defaultMessage, contains('频繁'));
    });
  });
}
