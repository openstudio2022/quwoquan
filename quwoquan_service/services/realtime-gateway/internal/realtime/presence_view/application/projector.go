package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

type Presence struct {
	AccountID  string
	DeviceID   string
	State      string
	ObservedAt time.Time
	ExpiresAt  time.Time
	Sequence   int64
}

type Store interface {
	UpsertIfNewer(context.Context, Presence) (bool, error)
	DeleteIfNotNewer(context.Context, string, string, int64) (bool, error)
}

type Projector struct{ store Store }

func NewProjector(store Store) *Projector { return &Projector{store: store} }

func (p *Projector) Project(ctx context.Context, presence Presence) (bool, error) {
	if p == nil || p.store == nil {
		return false, errors.New("presence view store is unavailable")
	}
	if strings.TrimSpace(presence.AccountID) == "" || strings.TrimSpace(presence.DeviceID) == "" || strings.TrimSpace(presence.State) == "" || presence.Sequence <= 0 || !presence.ExpiresAt.After(presence.ObservedAt) {
		return false, errors.New("presence projection is invalid")
	}
	return p.store.UpsertIfNewer(ctx, presence)
}
