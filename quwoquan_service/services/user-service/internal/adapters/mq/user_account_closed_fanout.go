package mq

import (
	"context"
	"errors"

	"quwoquan_service/services/user-service/internal/application"
	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
)

// UserAccountClosedFanout 以 durable stream 为提交条件；本服务的
// search/tag/realtime 投影随后执行，失败会使 outbox 保持未确认并重放。
type UserAccountClosedFanout struct {
	stream      *EventPublisher
	projections application.UserEventPublisher
}

func NewUserAccountClosedFanout(
	stream *EventPublisher,
	projections application.UserEventPublisher,
) (*UserAccountClosedFanout, error) {
	if stream == nil || projections == nil {
		return nil, errors.New(
			"UserAccountClosed fanout requires stream and projection publishers",
		)
	}
	return &UserAccountClosedFanout{
		stream:      stream,
		projections: projections,
	}, nil
}

func (fanout *UserAccountClosedFanout) PublishUserAccountClosed(
	ctx context.Context,
	event accountports.CloseOutboxEvent,
	payload map[string]any,
) error {
	if err := fanout.stream.AppendUserAccountClosed(
		ctx,
		event,
		payload,
	); err != nil {
		return err
	}
	return fanout.projections.PublishUserEvent(
		ctx,
		event.EventType,
		event.AccountID,
		event.AccountID,
		payload,
	)
}
