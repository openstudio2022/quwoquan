package redisstore

import (
	"context"
	"errors"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
)

type ResumableEventReader struct {
	transport runtimemessaging.CursorDeliveryTransport
}

func NewResumableEventReader(
	transport runtimemessaging.MessageTransport,
) (*ResumableEventReader, error) {
	reader, ok := transport.(runtimemessaging.CursorDeliveryTransport)
	if !ok {
		return nil, errors.New("realtime message transport does not support cursor reads")
	}
	return &ResumableEventReader{transport: reader}, nil
}

func (reader *ResumableEventReader) ReadAfter(
	ctx context.Context,
	identity application.TrustedIdentity,
	cursor string,
	count int64,
	block time.Duration,
) ([]application.ResumableEvent, error) {
	accountID := strings.TrimSpace(identity.AccountID)
	if accountID == "" {
		return nil, errors.New("resumable event read requires trusted account identity")
	}
	records, err := reader.transport.ReadDurableAfter(
		ctx,
		runtimemessaging.CursorReadRequest{
			Stream: runtimemessaging.RealtimeChatResumeStream(accountID),
			Cursor: cursor,
			Count:  count,
			Block:  block,
		},
	)
	if err != nil {
		return nil, err
	}
	events := make([]application.ResumableEvent, 0, len(records))
	for _, record := range records {
		var payload string
		for _, field := range record.Fields {
			if field.Name == "payload" {
				payload = field.Value
				break
			}
		}
		if strings.TrimSpace(payload) == "" {
			continue
		}
		events = append(events, application.ResumableEvent{
			Cursor:  record.ID,
			Payload: []byte(payload),
		})
	}
	return events, nil
}
