package application

import (
	"context"
	"errors"
	"strings"
)

var ErrInvalidCursor = errors.New("invalid ChatInboxView cursor")

type Reader struct{ store Store }

func NewReader(store Store) *Reader {
	if store == nil {
		panic("ChatInboxView store is required")
	}
	return &Reader{store: store}
}

func (reader *Reader) List(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) (Page, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return Page{}, errors.New("ChatInboxView persona identity is required")
	}
	if limit <= 0 {
		limit = 50
	}
	return reader.store.List(ctx, userID, limit, cursor)
}
