package preferencefact

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	preferencemodel "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/model"
	preferenceports "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/ports"
)

type ListPreferencesQuery struct {
	UserID         string
	Scope          string
	ConversationID string
	Status         string
	Limit          int
}

type PreferenceFactListView struct {
	Items []preferencemodel.Fact `json:"items"`
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
) (_ PreferenceFactListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.ListAssistantPreferences",
		attribute.String("preference.scope", strings.TrimSpace(query.Scope)),
		attribute.String("preference.status", strings.TrimSpace(query.Status)),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	userID := strings.TrimSpace(query.UserID)
	if userID == "" {
		return PreferenceFactListView{}, preferenceInvalidArgument("missing trusted persona")
	}
	scope := preferencemodel.Scope(strings.TrimSpace(query.Scope))
	switch scope {
	case "", preferencemodel.ScopeSession, preferencemodel.ScopeLongTerm:
	default:
		return PreferenceFactListView{}, preferenceInvalidArgument("invalid preference scope")
	}
	conversationID := strings.TrimSpace(query.ConversationID)
	if scope == preferencemodel.ScopeLongTerm && conversationID != "" {
		return PreferenceFactListView{}, preferenceInvalidArgument(
			"long_term preference query cannot bind conversation",
		)
	}
	status := preferencemodel.Status(strings.TrimSpace(query.Status))
	if status == "" {
		status = preferencemodel.StatusActive
	}
	switch status {
	case preferencemodel.StatusActive, preferencemodel.StatusRevoked:
	default:
		return PreferenceFactListView{}, preferenceInvalidArgument("invalid preference status")
	}
	limit := query.Limit
	if limit <= 0 {
		limit = 50
	}
	if limit > 100 {
		limit = 100
	}
	if f == nil || f.reader == nil {
		return PreferenceFactListView{}, preferenceStorageUnavailable(
			"assistant preference reader is not configured",
		)
	}
	items, readErr := f.reader.List(ctx, userID, preferenceports.ListFilter{
		Scope:          scope,
		ConversationID: conversationID,
		Status:         status,
		Limit:          limit,
	})
	if readErr != nil {
		return PreferenceFactListView{}, preferenceStorageUnavailable(readErr.Error())
	}
	if items == nil {
		items = []preferencemodel.Fact{}
	}
	return PreferenceFactListView{Items: items}, nil
}

func (f *QueryFacade) ResolveActiveSnapshots(
	ctx context.Context,
	userID string,
	conversationID string,
) ([]preferencemodel.Snapshot, []preferencemodel.Snapshot, error) {
	if f == nil || f.reader == nil {
		return nil, nil, preferenceStorageUnavailable(
			"assistant preference reader is not configured",
		)
	}
	facts, err := f.reader.ListActiveForRun(
		ctx,
		strings.TrimSpace(userID),
		strings.TrimSpace(conversationID),
		16,
	)
	if err != nil {
		return nil, nil, preferenceStorageUnavailable(err.Error())
	}
	sessionFacts := make([]preferencemodel.Fact, 0, 4)
	longTermFacts := make([]preferencemodel.Fact, 0, 4)
	for _, fact := range facts {
		switch fact.Scope {
		case preferencemodel.ScopeSession:
			if len(sessionFacts) < 16 {
				sessionFacts = append(sessionFacts, fact)
			}
		case preferencemodel.ScopeLongTerm:
			if len(longTermFacts) < 16 {
				longTermFacts = append(longTermFacts, fact)
			}
		}
	}
	return preferenceSnapshots(sessionFacts), preferenceSnapshots(longTermFacts), nil
}

func preferenceSnapshots(facts []preferencemodel.Fact) []preferencemodel.Snapshot {
	out := make([]preferencemodel.Snapshot, 0, len(facts))
	for _, fact := range facts {
		out = append(out, fact.Snapshot())
	}
	return out
}
