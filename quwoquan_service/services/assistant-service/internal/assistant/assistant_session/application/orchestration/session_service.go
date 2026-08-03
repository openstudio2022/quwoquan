package orchestration

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtid "quwoquan_service/runtime/id"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

func (service *AssistantService) requireSessionStore() (ports.SessionStore, error) {
	if service.sessions == nil {
		return nil, assistantSessionStorageUnavailable(
			"assistant session store is not configured",
		)
	}
	return service.sessions, nil
}

func (service *AssistantService) CreateSession(
	ctx context.Context,
	userID string,
	input assistant.CreateSessionInput,
) (_ assistant.AssistantSession, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.CreateSession",
		attribute.String("user.id", userID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := service.requireSessionStore()
	if err != nil {
		return assistant.AssistantSession{}, err
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.AssistantSession{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"userId 不能为空",
			"missing userId",
		)
	}
	input.ClientRequestID = strings.TrimSpace(input.ClientRequestID)
	if input.ClientRequestID == "" {
		return assistant.AssistantSession{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"clientRequestId 不能为空",
			"missing clientRequestId",
		)
	}
	sessionID, err := rtid.Generate(rtid.PrefixAssistantSession)
	if err != nil {
		return assistant.AssistantSession{}, rterr.NewUnavailable(
			rterr.ModuleAssistant,
			"生成对话 ID 失败",
			err.Error(),
		)
	}
	now := service.now()
	session := assistant.AssistantSession{
		SessionID:       sessionID,
		UserID:          userID,
		State:           "active",
		Summary:         strings.TrimSpace(input.Summary),
		ClientRequestID: input.ClientRequestID,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	stored, _, err := store.InsertSession(ctx, session)
	if err != nil {
		return assistant.AssistantSession{}, assistantSessionStorageUnavailable(err.Error())
	}
	return stored, nil
}

func (service *AssistantService) GetSession(
	ctx context.Context,
	userID string,
	sessionID string,
) (_ assistant.AssistantSession, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.GetSession",
		attribute.String("user.id", userID),
		attribute.String("session.id", sessionID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := service.requireSessionStore()
	if err != nil {
		return assistant.AssistantSession{}, err
	}
	userID = strings.TrimSpace(userID)
	sessionID = strings.TrimSpace(sessionID)
	session, found, err := store.GetSession(ctx, sessionID)
	if err != nil {
		return assistant.AssistantSession{}, assistantSessionStorageUnavailable(err.Error())
	}
	if !found || session.UserID != userID {
		return assistant.AssistantSession{}, assistantSessionNotFound()
	}
	return session, nil
}

func (service *AssistantService) ListSessions(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) (_ assistant.AssistantSessionListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.ListSessions",
		attribute.String("user.id", userID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	store, err := service.requireSessionStore()
	if err != nil {
		return assistant.AssistantSessionListView{}, err
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.AssistantSessionListView{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"userId 不能为空",
			"missing userId",
		)
	}
	items, nextCursor, err := store.ListSessions(
		ctx,
		userID,
		limit,
		strings.TrimSpace(cursor),
	)
	if err != nil {
		if strings.Contains(err.Error(), "invalid sessions cursor") {
			return assistant.AssistantSessionListView{}, rterr.NewInvalidArgument(
				rterr.ModuleAssistant,
				"分页游标无效",
				err.Error(),
			)
		}
		return assistant.AssistantSessionListView{},
			assistantSessionStorageUnavailable(err.Error())
	}
	return assistant.AssistantSessionListView{
		Items:      items,
		NextCursor: nextCursor,
	}, nil
}
