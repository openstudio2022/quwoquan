package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

type Profile struct {
	CreatorID     string
	DisplayName   string
	AvatarURL     string
	FollowerCount int64
	PostCount     int64
	SourceVersion int64
	UpdatedAt     time.Time
}

type Store interface {
	UpsertIfNewer(context.Context, Profile) (bool, error)
	DeleteIfNotOlder(context.Context, string, int64) (bool, error)
}

type Projector struct{ store Store }

func NewProjector(store Store) *Projector { return &Projector{store: store} }

func (p *Projector) Project(ctx context.Context, profile Profile) (bool, error) {
	if p == nil || p.store == nil {
		return false, errors.New("creator runtime profile store is unavailable")
	}
	if strings.TrimSpace(profile.CreatorID) == "" || strings.TrimSpace(profile.DisplayName) == "" || profile.SourceVersion <= 0 || profile.FollowerCount < 0 || profile.PostCount < 0 {
		return false, errors.New("creator runtime profile is invalid")
	}
	return p.store.UpsertIfNewer(ctx, profile)
}

func (p *Projector) Delete(ctx context.Context, creatorID string, sourceVersion int64) (bool, error) {
	if p == nil || p.store == nil {
		return false, errors.New("creator runtime profile store is unavailable")
	}
	if strings.TrimSpace(creatorID) == "" || sourceVersion <= 0 {
		return false, errors.New("creator runtime profile tombstone identity and sourceVersion are required")
	}
	return p.store.DeleteIfNotOlder(ctx, strings.TrimSpace(creatorID), sourceVersion)
}
