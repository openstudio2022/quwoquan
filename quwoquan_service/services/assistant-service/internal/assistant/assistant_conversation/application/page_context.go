package application

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"
	"unicode"

	rtredis "quwoquan_service/runtime/redis"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

const (
	maxPageContextObjects = 20
	maxPageContextActions = 20
)

func pageContextKey(userID string) string {
	return "page_ctx:" + strings.TrimSpace(userID)
}

func (s *AssistantService) storePageContext(
	ctx context.Context,
	userID string,
	raw assistant.AssistantContextSnapshot,
) (assistant.PageContextAck, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.PageContextAck{}, runerrors.AppErrorFromRunInvalidArgument(
			"page context userId is required",
		)
	}
	now := s.now()
	snapshot, err := normalizePageContextSnapshot(raw, now)
	if err != nil {
		return assistant.PageContextAck{}, runerrors.AppErrorFromRunInvalidArgument(
			err.Error(),
		)
	}
	if s.cache == nil {
		return assistant.PageContextAck{}, runerrors.AppErrorFromPageContextUnavailable(
			"page context cache is not configured",
		)
	}
	payload, err := json.Marshal(snapshot)
	if err != nil {
		return assistant.PageContextAck{}, runerrors.AppErrorFromPageContextUnavailable(
			"encode page context: " + err.Error(),
		)
	}
	if err := s.cache.Set(
		ctx,
		pageContextKey(userID),
		string(payload),
		pageContextTTL,
	); err != nil {
		return assistant.PageContextAck{}, runerrors.AppErrorFromPageContextUnavailable(
			"store page context: " + err.Error(),
		)
	}
	expiresAt := now.Add(pageContextTTL)
	return assistant.PageContextAck{
		Accepted:   true,
		ContextKey: pageContextKey(userID),
		ExpiresAt:  &expiresAt,
	}, nil
}

func (s *AssistantService) loadPageContext(
	ctx context.Context,
	userID string,
) *assistant.AssistantContextSnapshot {
	if s.cache == nil {
		return nil
	}
	key := pageContextKey(userID)
	payload, err := s.cache.Get(ctx, key)
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return nil
	}
	if err != nil {
		slog.WarnContext(
			ctx,
			"assistant page context read failed; continuing without page context",
			slog.String("error", err.Error()),
		)
		return nil
	}
	var snapshot assistant.AssistantContextSnapshot
	if err := json.Unmarshal([]byte(payload), &snapshot); err != nil {
		slog.WarnContext(
			ctx,
			"assistant page context decode failed; dropping invalid snapshot",
			slog.String("error", err.Error()),
		)
		if deleteErr := s.cache.Del(ctx, key); deleteErr != nil {
			slog.WarnContext(
				ctx,
				"assistant invalid page context cleanup failed",
				slog.String("error", deleteErr.Error()),
			)
		}
		return nil
	}
	normalized, err := normalizePageContextSnapshot(snapshot, s.now())
	if err != nil {
		return nil
	}
	return &normalized
}

func normalizePageContextSnapshot(
	raw assistant.AssistantContextSnapshot,
	now time.Time,
) (assistant.AssistantContextSnapshot, error) {
	pageContextType, parseErr := assistantgenerated.ParseAssistantPageContextType(
		raw.PageType,
	)
	if parseErr != nil ||
		pageContextType == assistantgenerated.AssistantPageContextTypeUnknown {
		return assistant.AssistantContextSnapshot{}, fmt.Errorf(
			"page context pageType is invalid",
		)
	}
	pageType := pageContextType.WireName()
	capturedAt := raw.CapturedAt.UTC()
	if capturedAt.IsZero() ||
		capturedAt.After(now.Add(time.Minute)) ||
		capturedAt.Before(now.Add(-pageContextTTL)) {
		return assistant.AssistantContextSnapshot{}, fmt.Errorf(
			"page context capturedAt is outside the accepted freshness window",
		)
	}
	if (len(raw.PageObjects) > 0 || len(raw.UserActions) > 0) &&
		(raw.ConsentMatrix == nil || !raw.ConsentMatrix.CanReadCurrentPage) {
		return assistant.AssistantContextSnapshot{}, fmt.Errorf(
			"page context current-page consent is required",
		)
	}
	if len(raw.PageObjects) > maxPageContextObjects {
		return assistant.AssistantContextSnapshot{}, fmt.Errorf(
			"page context contains too many object references",
		)
	}
	if len(raw.UserActions) > maxPageContextActions {
		return assistant.AssistantContextSnapshot{}, fmt.Errorf(
			"page context contains too many user actions",
		)
	}
	if len(raw.IntersectionEvidenceRefs) > 0 {
		return assistant.AssistantContextSnapshot{}, fmt.Errorf(
			"page context cannot carry intersection evidence references",
		)
	}

	objects := make([]assistant.AssistantPageObjectRef, 0, len(raw.PageObjects))
	seenObjects := map[string]struct{}{}
	for _, rawObject := range raw.PageObjects {
		objectTypeRef := strings.TrimSpace(rawObject.ObjectTypeRef)
		objectID := strings.TrimSpace(rawObject.ObjectID)
		destination, ok := citationDestinationFromSearch(
			objectTypeRef,
			objectID,
			"",
		)
		if !ok || destination.ObjectTypeRef == "" || !validContextValue(objectID, 256) {
			return assistant.AssistantContextSnapshot{}, fmt.Errorf(
				"page context contains an invalid object reference",
			)
		}
		key := destination.ObjectTypeRef + ":" + destination.ObjectID
		if _, exists := seenObjects[key]; exists {
			continue
		}
		seenObjects[key] = struct{}{}
		objects = append(objects, assistant.AssistantPageObjectRef{
			ObjectTypeRef: destination.ObjectTypeRef,
			ObjectID:      destination.ObjectID,
		})
	}

	actions := make([]assistant.AssistantPageUserAction, 0, len(raw.UserActions))
	for _, rawAction := range raw.UserActions {
		action := strings.TrimSpace(rawAction.Action)
		if !validContextIdentifier(action, 96) {
			return assistant.AssistantContextSnapshot{}, fmt.Errorf(
				"page context contains an invalid user action",
			)
		}
		objectTypeRef := strings.TrimSpace(rawAction.ObjectTypeRef)
		objectID := strings.TrimSpace(rawAction.ObjectID)
		if (objectTypeRef == "") != (objectID == "") {
			return assistant.AssistantContextSnapshot{}, fmt.Errorf(
				"page context action object reference is incomplete",
			)
		}
		if objectTypeRef != "" {
			destination, ok := citationDestinationFromSearch(
				objectTypeRef,
				objectID,
				"",
			)
			if !ok || destination.ObjectTypeRef == "" || !validContextValue(objectID, 256) {
				return assistant.AssistantContextSnapshot{}, fmt.Errorf(
					"page context action object reference is invalid",
				)
			}
			objectTypeRef = destination.ObjectTypeRef
			objectID = destination.ObjectID
		}
		var occurredAt *time.Time
		if rawAction.OccurredAt != nil {
			normalizedOccurredAt := rawAction.OccurredAt.UTC()
			if normalizedOccurredAt.After(now.Add(time.Minute)) ||
				normalizedOccurredAt.Before(now.Add(-pageContextTTL)) {
				return assistant.AssistantContextSnapshot{}, fmt.Errorf(
					"page context user action occurredAt is outside the accepted freshness window",
				)
			}
			occurredAt = &normalizedOccurredAt
		}
		actions = append(actions, assistant.AssistantPageUserAction{
			Action:        action,
			ObjectTypeRef: objectTypeRef,
			ObjectID:      objectID,
			OccurredAt:    occurredAt,
		})
	}

	return assistant.AssistantContextSnapshot{
		CapturedAt:    capturedAt,
		PageType:      pageType,
		PageObjects:   objects,
		UserActions:   actions,
		ConsentMatrix: &assistant.AssistantContextConsent{CanReadCurrentPage: true},
	}, nil
}

func validContextIdentifier(value string, maxRunes int) bool {
	value = strings.TrimSpace(value)
	if value == "" || len([]rune(value)) > maxRunes {
		return false
	}
	for _, r := range value {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			continue
		}
		switch r {
		case '_', '-', '.', ':', '/':
			continue
		default:
			return false
		}
	}
	return true
}

func validContextValue(value string, maxRunes int) bool {
	value = strings.TrimSpace(value)
	if value == "" || len([]rune(value)) > maxRunes {
		return false
	}
	for _, r := range value {
		if unicode.IsControl(r) {
			return false
		}
	}
	return true
}

func FormatPageContextForPrompt(
	context *assistant.AssistantContextSnapshot,
) string {
	if context == nil {
		return ""
	}
	var b strings.Builder
	b.WriteString("\n当前页面结构化上下文（仅用于定位，不得据此虚构对象正文）：")
	b.WriteString("\n- pageType: ")
	b.WriteString(context.PageType)
	for _, object := range context.PageObjects {
		b.WriteString("\n- object: ")
		b.WriteString(object.ObjectTypeRef)
		b.WriteString(":")
		b.WriteString(object.ObjectID)
	}
	for _, action := range context.UserActions {
		b.WriteString("\n- userAction: ")
		b.WriteString(action.Action)
		if action.ObjectTypeRef != "" && action.ObjectID != "" {
			b.WriteString(" @ ")
			b.WriteString(action.ObjectTypeRef)
			b.WriteString(":")
			b.WriteString(action.ObjectID)
		}
	}
	return b.String()
}
