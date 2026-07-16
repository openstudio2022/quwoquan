package testsupport

import (
	"context"
	"sort"
	"strings"
	"sync"
	"time"

	postdomain "quwoquan_service/services/content-service/internal/domain/post"
)

// ShareInteractionStore is a local-contract fake for the share projection port.
type ShareInteractionStore struct {
	mu    sync.RWMutex
	items map[string]postdomain.ShareInteractionOccurrence
}

func NewShareInteractionStore() *ShareInteractionStore {
	return &ShareInteractionStore{items: make(map[string]postdomain.ShareInteractionOccurrence)}
}

func (s *ShareInteractionStore) Save(_ context.Context, item postdomain.ShareInteractionOccurrence) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.items[item.InteractionID]; !exists {
		s.items[item.InteractionID] = item
	}
	return nil
}

func (s *ShareInteractionStore) List(
	_ context.Context,
	query postdomain.ShareInteractionQuery,
) ([]postdomain.ShareInteractionOccurrence, bool, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]postdomain.ShareInteractionOccurrence, 0)
	for _, item := range s.items {
		matches := item.TargetSubAccountID == query.SubAccountID
		if query.Direction == "sent" {
			matches = item.ActorSubAccountID == query.SubAccountID
		}
		if !matches || !shareInteractionAfterCursor(item, query.CursorTime, query.CursorID) {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		if !items[i].OccurredAt.Equal(items[j].OccurredAt) {
			return items[i].OccurredAt.After(items[j].OccurredAt)
		}
		return items[i].InteractionID > items[j].InteractionID
	})
	hasMore := len(items) > query.Limit
	if hasMore {
		items = items[:query.Limit]
	}
	return items, hasMore, nil
}

func (s *ShareInteractionStore) MarkState(
	_ context.Context,
	subAccountID string,
	interactionID string,
	state string,
	at time.Time,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	item, ok := s.items[strings.TrimSpace(interactionID)]
	if !ok || item.TargetSubAccountID != strings.TrimSpace(subAccountID) {
		return nil
	}
	if item.SeenAt.IsZero() || at.Before(item.SeenAt) {
		item.SeenAt = at
	}
	if state == "read" && (item.ReadAt.IsZero() || at.Before(item.ReadAt)) {
		item.ReadAt = at
	}
	s.items[item.InteractionID] = item
	return nil
}

func shareInteractionAfterCursor(
	item postdomain.ShareInteractionOccurrence,
	cursorTime time.Time,
	cursorID string,
) bool {
	if cursorTime.IsZero() {
		return true
	}
	if item.OccurredAt.Before(cursorTime) {
		return true
	}
	return item.OccurredAt.Equal(cursorTime) && item.InteractionID < cursorID
}
