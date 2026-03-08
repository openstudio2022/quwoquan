// Code generated from contracts/metadata/user/user_profile/errors.yaml. DO NOT EDIT.
package generated

import (
	"errors"

	rerrors "quwoquan_service/runtime/errors"
)

//nolint:gochecknoglobals
var (
	ErrUserNotFound   = errors.New("USER.USER.not_found")
	ErrUnauthorized   = errors.New("USER.USER.unauthorized")
	ErrForbidden      = errors.New("USER.USER.forbidden")
	ErrNicknameTaken  = errors.New("USER.USER.nickname_taken")
	ErrInvalidArgument = errors.New("USER.USER.invalid_argument")
	ErrRateLimited    = errors.New("USER.USER.rate_limited")
	ErrInternalError  = errors.New("USER.SYSTEM.internal_error")
)

func AppErrorFromUserNotFound(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrUserNotFound.Error())
	return rerrors.NewAppError(code, "用户不存在", debugMessage, false)
}

func AppErrorFromUnauthorized(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrUnauthorized.Error())
	return rerrors.NewAppError(code, "请先登录", debugMessage, false)
}

func AppErrorFromForbidden(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrForbidden.Error())
	return rerrors.NewAppError(code, "无权访问该资源", debugMessage, false)
}

func AppErrorFromNicknameTaken(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrNicknameTaken.Error())
	return rerrors.NewAppError(code, "该昵称已被使用，请换一个", debugMessage, false)
}

func AppErrorFromInvalidArgument(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrInvalidArgument.Error())
	return rerrors.NewAppError(code, "请求参数有误", debugMessage, false)
}

func AppErrorFromRateLimited(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrRateLimited.Error())
	return rerrors.NewAppError(code, "操作太频繁，请稍后重试", debugMessage, true)
}

func AppErrorFromInternalError(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrInternalError.Error())
	return rerrors.NewAppError(code, "服务异常，请稍后重试", debugMessage, false)
}
