package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

type InboxItem struct {
	AccountID      string
	ConversationID string
	LastMessageID  string
	UnreadCount    int64
	UpdatedAt      time.Time
	Checkpoint     int64
}

type Store interface {
	UpsertIfNewer(context.Context, InboxItem) (bool, error)
	DeleteConversation(context.Context, string, string, int64) (bool, error)
}

type Projector struct{ store Store }

func NewProjector(store Store) *Projector { return &Projector{store: store} }

func (p *Projector) Project(ctx context.Context, item InboxItem) (bool, error) {
	if p == nil || p.store == nil {
		return false, errors.New("chat inbox projection store is unavailable")
	}
	if strings.TrimSpace(item.AccountID) == "" || strings.TrimSpace(item.ConversationID) == "" || item.Checkpoint <= 0 {
		return false, errors.New("chat inbox projection identity and checkpoint are required")
	}
	if item.UnreadCount < 0 {
		return false, errors.New("chat inbox unreadCount cannot be negative")
	}
	return p.store.UpsertIfNewer(ctx, item)
}
