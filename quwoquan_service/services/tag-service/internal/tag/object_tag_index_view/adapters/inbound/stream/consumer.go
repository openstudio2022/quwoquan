package stream

import (
	"context"
	"log/slog"
	"time"

	ports "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/domain/ports"
	objectmessaging "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/messaging"
)

// Consumer is the ObjectTagIndexView inbound lifecycle adapter. Durable
// transport details stay behind the object's infrastructure boundary.
type Consumer struct {
	transport *objectmessaging.UserProfileTagConsumer
}

func NewConsumer(
	transport objectmessaging.UserProfileTagTransport,
	projector ports.UserProfileTagProjector,
	consumerID string,
	logger *slog.Logger,
) (*Consumer, error) {
	inner, err := objectmessaging.NewUserProfileTagConsumer(
		transport,
		projector,
		consumerID,
		logger,
	)
	if err != nil {
		return nil, err
	}
	return &Consumer{transport: inner}, nil
}

func (consumer *Consumer) Run(ctx context.Context) {
	consumer.transport.Run(ctx)
}

func (consumer *Consumer) ProcessOnce(ctx context.Context) (int, error) {
	return consumer.transport.ProcessOnce(ctx)
}

func (consumer *Consumer) Healthy(maxStaleness time.Duration) error {
	return consumer.transport.Healthy(maxStaleness)
}
