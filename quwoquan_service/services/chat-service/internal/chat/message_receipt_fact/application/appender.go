package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

type Receipt struct {
	ReceiptID     string
	MessageID     string
	AccountID     string
	ReceiptType   string
	SourceEventID string
	OccurredAt    time.Time
	RecordedAt    time.Time
}

type Store interface {
	AppendIfAbsent(context.Context, Receipt) (Receipt, bool, error)
}

type Appender struct{ store Store }

func NewAppender(store Store) *Appender { return &Appender{store: store} }

func (a *Appender) Append(ctx context.Context, receipt Receipt) (Receipt, bool, error) {
	if a == nil || a.store == nil {
		return Receipt{}, false, errors.New("message receipt fact store is unavailable")
	}
	if strings.TrimSpace(receipt.ReceiptID) == "" || strings.TrimSpace(receipt.MessageID) == "" || strings.TrimSpace(receipt.AccountID) == "" || strings.TrimSpace(receipt.SourceEventID) == "" {
		return Receipt{}, false, errors.New("message receipt fact identity is incomplete")
	}
	if receipt.OccurredAt.IsZero() {
		return Receipt{}, false, errors.New("message receipt occurredAt is required")
	}
	if receipt.RecordedAt.IsZero() {
		receipt.RecordedAt = time.Now().UTC()
	}
	return a.store.AppendIfAbsent(ctx, receipt)
}
