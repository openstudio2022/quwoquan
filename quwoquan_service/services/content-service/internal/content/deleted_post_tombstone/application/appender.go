package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

type Tombstone struct {
	PostID        string
	AuthorID      string
	SourceEventID string
	DeletedAt     time.Time
	RecordedAt    time.Time
}

type Store interface {
	AppendIfAbsent(context.Context, Tombstone) (bool, error)
	Exists(context.Context, string) (bool, error)
}

type Appender struct{ store Store }

func NewAppender(store Store) *Appender { return &Appender{store: store} }

func (a *Appender) Append(ctx context.Context, tombstone Tombstone) (bool, error) {
	if a == nil || a.store == nil {
		return false, errors.New("deleted post tombstone store is unavailable")
	}
	if strings.TrimSpace(tombstone.PostID) == "" || strings.TrimSpace(tombstone.SourceEventID) == "" || tombstone.DeletedAt.IsZero() {
		return false, errors.New("deleted post tombstone identity and deletedAt are required")
	}
	if tombstone.RecordedAt.IsZero() {
		tombstone.RecordedAt = time.Now().UTC()
	}
	return a.store.AppendIfAbsent(ctx, tombstone)
}
