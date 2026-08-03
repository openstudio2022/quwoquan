package orchestration

import (
	"net/http"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

func WithSessionStore(store ports.SessionStore) AssistantServiceOption {
	return func(service *AssistantService) {
		service.sessions = store
	}
}

// 错误构造与 services/assistant-service/contracts/**/errors.yaml 同源；
// 合同测试锁定 code/status/user_message 一致性。

func assistantSessionNotFound() *rterr.AppError {
	appErr := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "session_not_found"),
		"对话不存在或已失效",
		"assistant session not found",
	)
	appErr.HTTPStatus = http.StatusNotFound
	return appErr
}

func assistantSessionStorageUnavailable(debug string) *rterr.AppError {
	appErr := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindSystem, "session_storage_unavailable"),
		"对话服务暂不可用，请稍后重试",
		debug,
	)
	appErr.HTTPStatus = http.StatusServiceUnavailable
	return appErr
}

func AssistantRunInvalidArgument(debug string) *rterr.AppError {
	appErr := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "run_invalid_argument"),
		"执行请求参数有误",
		debug,
	)
	appErr.HTTPStatus = http.StatusBadRequest
	return appErr
}
