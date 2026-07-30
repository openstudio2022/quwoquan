package orchestration

import (
	"net/http"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

func WithConversationRunStore(store ports.ConversationRunStore) AssistantServiceOption {
	return func(service *AssistantService) {
		service.conversationRuns = store
		if eventStore, ok := store.(AssistantRunEventStore); ok {
			service.runEvents = eventStore
		}
	}
}

// 错误构造与 services/assistant-service/contracts/**/errors.yaml 同源；
// 合同测试锁定 code/status/user_message 一致性。

func assistantConversationNotFound() *rterr.AppError {
	appErr := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "conversation_not_found"),
		"对话不存在或已失效",
		"assistant conversation not found",
	)
	appErr.HTTPStatus = http.StatusNotFound
	return appErr
}

func assistantConversationStorageUnavailable(debug string) *rterr.AppError {
	appErr := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindSystem, "conversation_storage_unavailable"),
		"对话服务暂不可用，请稍后重试",
		debug,
	)
	appErr.HTTPStatus = http.StatusServiceUnavailable
	return appErr
}

func assistantRunNotFound() *rterr.AppError {
	appErr := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindUser, "run_not_found"),
		"本次执行不存在或已失效",
		"assistant run not found",
	)
	appErr.HTTPStatus = http.StatusNotFound
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

func assistantRunStorageUnavailable(debug string) *rterr.AppError {
	appErr := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleAssistant, rterr.KindSystem, "run_storage_unavailable"),
		"助手执行服务暂不可用，请稍后重试",
		debug,
	)
	appErr.HTTPStatus = http.StatusServiceUnavailable
	return appErr
}
