// Code generated from contracts/metadata/user/user_profile/errors.yaml. DO NOT EDIT.

enum UserErrorCode {
  userNotFound('USER.USER.not_found', '用户不存在', 404),
  unauthorized('USER.USER.unauthorized', '请先登录', 401),
  forbidden('USER.USER.forbidden', '无权访问该资源', 403),
  nicknameTaken('USER.USER.nickname_taken', '该昵称已被使用，请换一个', 409),
  invalidArgument('USER.USER.invalid_argument', '请求参数有误', 400),
  rateLimited('USER.USER.rate_limited', '操作太频繁，请稍后重试', 429),
  internalError('USER.SYSTEM.internal_error', '服务异常，请稍后重试', 500);

  final String code;
  final String defaultMessage;
  final int httpStatus;

  const UserErrorCode(this.code, this.defaultMessage, this.httpStatus);

  static UserErrorCode? fromCode(String code) {
    for (final e in values) {
      if (e.code == code) return e;
    }
    return null;
  }
}
