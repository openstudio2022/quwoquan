// Hand-maintained from contracts/metadata/user/greeting_request/errors.yaml.
package generated

import (
	"errors"

	rerrors "quwoquan_service/runtime/errors"
)

//nolint:gochecknoglobals
var (
	ErrGreetingTargetBlockedSender    = errors.New("USER.GREETING.target_blocked_sender")
	ErrGreetingDuplicatePending       = errors.New("USER.GREETING.duplicate_pending")
	ErrGreetingRateLimited            = errors.New("USER.GREETING.rate_limited")
	ErrGreetingAlreadyContact         = errors.New("USER.GREETING.already_contact")
	ErrGreetingNotFound               = errors.New("USER.GREETING.not_found")
	ErrGreetingInvalidStatusTransition = errors.New("USER.GREETING.invalid_status_transition")
)

func AppErrorFromGreetingTargetBlockedSender(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrGreetingTargetBlockedSender.Error())
	return rerrors.NewAppError(code, "发送失败，对方不接收你的打招呼", debugMessage)
}

func AppErrorFromGreetingDuplicatePending(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrGreetingDuplicatePending.Error())
	return rerrors.NewAppError(code, "已发送过打招呼，请等待对方回复", debugMessage)
}

func AppErrorFromGreetingRateLimited(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrGreetingRateLimited.Error())
	return rerrors.NewAppError(code, "打招呼发送频率超限，请稍后再试", debugMessage)
}

func AppErrorFromGreetingAlreadyContact(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrGreetingAlreadyContact.Error())
	return rerrors.NewAppError(code, "已互相关注，可直接发消息", debugMessage)
}

func AppErrorFromGreetingNotFound(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrGreetingNotFound.Error())
	return rerrors.NewAppError(code, "打招呼请求不存在", debugMessage)
}

func AppErrorFromGreetingInvalidStatusTransition(debugMessage string) *rerrors.AppError {
	code, _ := rerrors.ParseCode(ErrGreetingInvalidStatusTransition.Error())
	return rerrors.NewAppError(code, "操作不可用，请求状态已变更", debugMessage)
}
