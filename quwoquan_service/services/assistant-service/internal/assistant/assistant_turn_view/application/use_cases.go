package application

import (
	"context"
	"errors"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	sessionerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	turnviewmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/domain/model"
)

// Reader is the AssistantTurnView object boundary. The projection owns only
// terminal session history; run commands and live event transport do not
// cross this interface.
type Reader interface {
	ListSessionTurns(context.Context, string, string, int, string) (turnviewmodel.AssistantTurnListView, error)
}

type SessionOwnerReader interface {
	OwnedSessionExists(context.Context, string, string) (bool, error)
}

type QueryFacade struct {
	reader       Reader
	sessions     SessionOwnerReader
	synchronizer Synchronizer
}

func NewQueryFacade(
	reader Reader,
	sessions SessionOwnerReader,
	synchronizer Synchronizer,
) *QueryFacade {
	if reader == nil || sessions == nil || synchronizer == nil {
		panic("assistant turn view query dependencies are required")
	}
	return &QueryFacade{
		reader:       reader,
		sessions:     sessions,
		synchronizer: synchronizer,
	}
}

func (f *QueryFacade) ListSessionTurns(
	ctx context.Context,
	userID string,
	sessionID string,
	limit int,
	cursor string,
) (_ turnviewmodel.AssistantTurnListView, err error) {
	userID = strings.TrimSpace(userID)
	sessionID = strings.TrimSpace(sessionID)
	cursor = strings.TrimSpace(cursor)
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.ListSessionTurns",
		attribute.String("user.id", userID),
		attribute.String("session.id", sessionID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	if userID == "" || sessionID == "" {
		return turnviewmodel.AssistantTurnListView{},
			runerrors.AppErrorFromRunInvalidArgument(
				"assistant turn view requires owner and sessionId",
			)
	}
	if limit <= 0 {
		limit = 20
	}
	if limit > 50 {
		limit = 50
	}
	owned, ownerErr := f.sessions.OwnedSessionExists(ctx, userID, sessionID)
	if ownerErr != nil {
		return turnviewmodel.AssistantTurnListView{},
			runerrors.AppErrorFromRunStorageUnavailable(ownerErr.Error())
	}
	if !owned {
		return turnviewmodel.AssistantTurnListView{},
			sessionerrors.AppErrorFromSessionNotFound(
				turnviewmodel.ErrSessionNotFound.Error(),
			)
	}
	if syncErr := f.synchronizer.CatchUp(ctx); syncErr != nil {
		return turnviewmodel.AssistantTurnListView{},
			runerrors.AppErrorFromRunStorageUnavailable(syncErr.Error())
	}
	view, readErr := f.reader.ListSessionTurns(
		ctx,
		userID,
		sessionID,
		limit,
		cursor,
	)
	if readErr == nil {
		if view.Items == nil {
			view.Items = []turnviewmodel.AssistantTurnSummaryView{}
		}
		return view, nil
	}
	switch {
	case errors.Is(readErr, turnviewmodel.ErrSessionNotFound):
		return turnviewmodel.AssistantTurnListView{},
			sessionerrors.AppErrorFromSessionNotFound(readErr.Error())
	case errors.Is(readErr, turnviewmodel.ErrInvalidCursor):
		return turnviewmodel.AssistantTurnListView{},
			runerrors.AppErrorFromRunInvalidArgument(readErr.Error())
	default:
		return turnviewmodel.AssistantTurnListView{},
			runerrors.AppErrorFromRunStorageUnavailable(readErr.Error())
	}
}
