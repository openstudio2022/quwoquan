package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

type SearchItem struct {
	CircleID      string
	DisplayName   string
	Description   string
	Visibility    string
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
		return false, errors.New("circle search index is unavailable")
	}
	if strings.TrimSpace(item.CircleID) == "" || strings.TrimSpace(item.DisplayName) == "" || item.SourceVersion <= 0 {
		return false, errors.New("circle search item identity, displayName and sourceVersion are required")
	}
	return p.index.UpsertIfNewer(ctx, item)
}
