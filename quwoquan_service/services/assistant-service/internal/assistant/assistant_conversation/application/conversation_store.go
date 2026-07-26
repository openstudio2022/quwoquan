package application

import (
	"context"
	"net/http"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

// ConversationRunStore 是 AssistantConversation 与 AssistantRun(Turn) 两个聚合的
// 对象专属持久化端口。业务状态一律持久化，禁止进程内 map 承载：
//   - 一次创建（conversation/turn）由 userId+clientRequestId 唯一约束承载幂等，
//     重放返回首个聚合（聚合自身即 receipt，与 Post 发布同型）。
//   - turn 完成为 running -> completed/failed 的内部 CAS；已终态重复完成幂等返回存量。
type ConversationRunStore interface {
	InsertConversation(
		ctx context.Context,
		conversation assistant.AssistantConversation,
	) (assistant.AssistantConversation, bool, error)
	GetConversation(
		ctx context.Context,
		conversationID string,
	) (assistant.AssistantConversation, bool, error)
	UpdateConversationTurnPointer(
		ctx context.Context,
		conversationID string,
		activeTurnID string,
		lastTurnID string,
		updatedAt time.Time,
	) error
	InsertTurn(
		ctx context.Context,
		turn assistant.AssistantTurn,
	) (assistant.AssistantTurn, bool, error)
	GetTurn(
		ctx context.Context,
		turnID string,
	) (assistant.AssistantTurn, bool, error)
	GetTurnByClientRequest(
		ctx context.Context,
		userID string,
		conversationID string,
		clientRequestID string,
	) (assistant.AssistantTurn, bool, error)
	CompleteTurn(
		ctx context.Context,
		turn assistant.AssistantTurn,
	) (assistant.AssistantTurn, error)
	ListCompletedTurns(
		ctx context.Context,
		userID string,
		conversationID string,
		limit int,
	) ([]assistant.AssistantTurn, error)
	// ListConversations 按 owner 返回会话切片：updatedAt desc + conversationId
	// tiebreak 的 keyset 分页；cursor 为空表示第一页，返回的 nextCursor 为空表示无更多。
	ListConversations(
		ctx context.Context,
		userID string,
		limit int,
		cursor string,
	) ([]assistant.AssistantConversation, string, error)
	// ListTurns 按会话返回终态轮次切片：createdAt desc + turnId tiebreak 的
	// keyset 分页；只包含 completed/failed/cancelled 终态。
	ListTurns(
		ctx context.Context,
		userID string,
		conversationID string,
		limit int,
		cursor string,
	) ([]assistant.AssistantTurn, string, error)
}

func WithConversationRunStore(store ConversationRunStore) AssistantServiceOption {
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
