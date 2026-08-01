package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

type SearchItem struct {
	HomepageID    string
	EntityID      string
	DisplayName   string
	EntityType    string
	SourceVersion int64
	UpdatedAt     time.Time
}

type Index interface {
	UpsertIfNewer(context.Context, SearchItem) (bool, error)
	DeleteIfNotOlder(context.Context, string, int64) (bool, error)
}

type Projector struct{ index Index }

func NewProjector(index Index) *Projector { return &Projector{index: index} }

func (p *Projector) Upsert(ctx context.Context, item SearchItem) (bool, error) {
	if p == nil || p.index == nil {
		return false, errors.New("homepage search index is unavailable")
	}
	if strings.TrimSpace(item.HomepageID) == "" || strings.TrimSpace(item.EntityID) == "" || strings.TrimSpace(item.DisplayName) == "" || item.SourceVersion <= 0 {
		return false, errors.New("homepage search item identity, displayName and sourceVersion are required")
	}
	return p.index.UpsertIfNewer(ctx, item)
}
