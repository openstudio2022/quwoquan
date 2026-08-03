package application

import (
	"context"
	"errors"

	receiptmodel "quwoquan_service/services/chat-service/internal/chat/message_receipt_fact/domain/model"
)

type Store interface {
	AppendIfAbsent(context.Context, receiptmodel.Fact) (receiptmodel.Fact, bool, error)
	ListByMessage(context.Context, string) ([]receiptmodel.Fact, error)
}

type Appender struct{ store Store }

func NewAppender(store Store) *Appender {
	if store == nil {
		panic("message receipt fact store is required")
	}
	return &Appender{store: store}
}

func (a *Appender) Append(
	ctx context.Context,
	receipt receiptmodel.Fact,
) (receiptmodel.Fact, bool, error) {
	if a == nil || a.store == nil {
		return receiptmodel.Fact{}, false, errors.New("message receipt fact store is unavailable")
	}
	if err := receipt.Validate(); err != nil {
		return receiptmodel.Fact{}, false, err
	}
	return a.store.AppendIfAbsent(ctx, receipt)
}

func (a *Appender) ListByMessage(
	ctx context.Context,
	messageID string,
) ([]receiptmodel.Fact, error) {
	if a == nil || a.store == nil {
		return nil, errors.New("message receipt fact store is unavailable")
	}
	if messageID == "" {
		return nil, receiptmodel.ErrIdentityIncomplete
	}
	return a.store.ListByMessage(ctx, messageID)
}
