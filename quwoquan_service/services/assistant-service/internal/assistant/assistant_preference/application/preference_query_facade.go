package preferenceapplication

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	preferenceports "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/ports"
)

type ListPreferencesQuery struct {
	UserID    string
	Scope     string
	SessionID string
	Status    string
	Limit     int
}

type AssistantPreferenceListView struct {
	Items []preferencemodel.AssistantPreference `json:"items"`
}

type QueryFacade struct {
	reader preferenceports.Reader
}

func NewQueryFacade(reader preferenceports.Reader) *QueryFacade {
	return &QueryFacade{reader: reader}
}

func (f *QueryFacade) ListPreferences(
	ctx context.Context,
	query ListPreferencesQuery,
) (_ AssistantPreferenceListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.ListAssistantPreferences",
		attribute.String("preference.scope", strings.TrimSpace(query.Scope)),
		attribute.String("preference.status", strings.TrimSpace(query.Status)),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	userID := strings.TrimSpace(query.UserID)
	if userID == "" {
		return AssistantPreferenceListView{}, preferenceInvalidArgument("missing trusted persona")
	}
	scope := preferencemodel.Scope(strings.TrimSpace(query.Scope))
	switch scope {
	case "", preferencemodel.ScopeSession, preferencemodel.ScopeLongTerm:
	default:
		return AssistantPreferenceListView{}, preferenceInvalidArgument("invalid preference scope")
	}
	sessionID := strings.TrimSpace(query.SessionID)
	if scope == preferencemodel.ScopeLongTerm && sessionID != "" {
		return AssistantPreferenceListView{}, preferenceInvalidArgument(
			"long_term preference query cannot bind session",
		)
	}
	status := preferencemodel.Status(strings.TrimSpace(query.Status))
	if status == "" {
		status = preferencemodel.StatusActive
	}
	switch status {
	case preferencemodel.StatusActive, preferencemodel.StatusRevoked:
	default:
		return AssistantPreferenceListView{}, preferenceInvalidArgument("invalid preference status")
	}
	limit := query.Limit
	if limit <= 0 {
		limit = 50
	}
	if limit > 100 {
		limit = 100
	}
	if f == nil || f.reader == nil {
		return AssistantPreferenceListView{}, preferenceStorageUnavailable(
			"assistant preference reader is not configured",
		)
	}
	items, readErr := f.reader.List(ctx, userID, preferenceports.ListFilter{
		Scope:     scope,
		SessionID: sessionID,
		Status:    status,
		Limit:     limit,
	})
	if readErr != nil {
		return AssistantPreferenceListView{}, preferenceStorageUnavailable(readErr.Error())
	}
	if items == nil {
		items = []preferencemodel.AssistantPreference{}
	}
	return AssistantPreferenceListView{Items: items}, nil
}

func (f *QueryFacade) ResolveActiveSnapshots(
	ctx context.Context,
	userID string,
	sessionID string,
) ([]preferencemodel.AssistantPreferenceSnapshot, []preferencemodel.AssistantPreferenceSnapshot, error) {
	if f == nil || f.reader == nil {
		return nil, nil, preferenceStorageUnavailable(
			"assistant preference reader is not configured",
		)
	}
	preferences, err := f.reader.ListActiveForRun(
		ctx,
		strings.TrimSpace(userID),
		strings.TrimSpace(sessionID),
		16,
	)
	if err != nil {
		return nil, nil, preferenceStorageUnavailable(err.Error())
	}
	sessionPreferences := make([]preferencemodel.AssistantPreference, 0, 4)
	longTermPreferences := make([]preferencemodel.AssistantPreference, 0, 4)
	for _, preference := range preferences {
		switch preference.Scope {
		case preferencemodel.ScopeSession:
			if len(sessionPreferences) < 16 {
				sessionPreferences = append(sessionPreferences, preference)
			}
		case preferencemodel.ScopeLongTerm:
			if len(longTermPreferences) < 16 {
				longTermPreferences = append(longTermPreferences, preference)
			}
		}
	}
	return preferenceSnapshots(sessionPreferences), preferenceSnapshots(longTermPreferences), nil
}

func preferenceSnapshots(preferences []preferencemodel.AssistantPreference) []preferencemodel.AssistantPreferenceSnapshot {
	out := make([]preferencemodel.AssistantPreferenceSnapshot, 0, len(preferences))
	for _, preference := range preferences {
		out = append(out, preference.Snapshot())
	}
	return out
}
