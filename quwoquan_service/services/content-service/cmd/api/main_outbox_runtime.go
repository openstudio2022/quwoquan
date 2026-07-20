package main

import (
	"context"
	"log/slog"
	"time"

	rthealth "quwoquan_service/runtime/health"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	outboundshareapp "quwoquan_service/services/content-service/internal/application/content/outbound_share_fact/command"
	profileinteractionapp "quwoquan_service/services/content-service/internal/application/content/profile_interaction"
	moderationapp "quwoquan_service/services/content-service/internal/application/moderation"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	reportapp "quwoquan_service/services/content-service/internal/application/report"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	shareports "quwoquan_service/services/content-service/internal/domain/content/outbound_share_fact/ports"
	readfactports "quwoquan_service/services/content-service/internal/domain/content/profile_interaction_read_fact/ports"
	moderationports "quwoquan_service/services/content-service/internal/domain/moderation/ports"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	reactionports "quwoquan_service/services/content-service/internal/domain/reaction/ports"
	reportports "quwoquan_service/services/content-service/internal/domain/report/ports"
)

func startOutboundShareOutboxRelay(
	ctx context.Context,
	reader shareports.OutboxReader,
	checkpoints shareports.ProjectionCheckpointStore,
	publisher shareports.OutboxPublisher,
	consumer string,
	healthName string,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) *outboundshareapp.OutboxRelay {
	relay := outboundshareapp.NewOutboxRelay(reader, checkpoints, publisher, consumer)
	go func() {
		if err := relay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			logger.Error("OutboundShareFact outbox relay stopped", "consumer", consumer, "error", err)
		}
	}()
	healthChecker.Register(healthName, func(_ context.Context) error {
		return relay.Healthy(5 * time.Second)
	})
	return relay
}

func startProfileInteractionReadFactRelay(
	ctx context.Context,
	reader readfactports.OutboxReader,
	checkpoints readfactports.ProjectionCheckpointStore,
	publisher readfactports.OutboxPublisher,
	consumer string,
	healthName string,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) *profileinteractionapp.ReadFactOutboxRelay {
	relay := profileinteractionapp.NewReadFactOutboxRelay(
		reader,
		checkpoints,
		publisher,
		consumer,
	)
	go func() {
		if err := relay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			logger.Error("ProfileInteractionReadFact relay stopped", "consumer", consumer, "error", err)
		}
	}()
	healthChecker.Register(healthName, func(_ context.Context) error {
		return relay.Healthy(5 * time.Second)
	})
	return relay
}

func startCommentOutboxRelay(
	ctx context.Context,
	reader commentports.OutboxReader,
	checkpoints commentports.ProjectionCheckpointStore,
	publisher commentports.OutboxPublisher,
	consumer string,
	healthName string,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) *commentapp.OutboxRelay {
	relay := commentapp.NewOutboxRelay(reader, checkpoints, publisher, consumer)
	go func() {
		if err := relay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			logger.Error("Comment outbox relay stopped", "consumer", consumer, "error", err)
		}
	}()
	healthChecker.Register(healthName, func(_ context.Context) error {
		return relay.Healthy(5 * time.Second)
	})
	return relay
}

// startPostOutboxRelay owns one Post consumer checkpoint. Callers must start a
// separate relay per external transport or derived read model; sharing a
// fan-out publisher would make partial delivery indistinguishable from a fully
// converged consumer.
func startPostOutboxRelay(
	ctx context.Context,
	reader postports.OutboxReader,
	checkpoints postports.ProjectionCheckpointStore,
	publisher postports.OutboxPublisher,
	consumer string,
	healthName string,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) *postapp.OutboxRelay {
	relay := postapp.NewOutboxRelay(reader, checkpoints, publisher, consumer)
	go func() {
		if err := relay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			logger.Error("content post outbox relay stopped", "consumer", consumer, "error", err)
		}
	}()
	healthChecker.Register(healthName, func(_ context.Context) error {
		return relay.Healthy(5 * time.Second)
	})
	return relay
}

// startReactionOutboxRelay 为外部事件与每个 reaction projection 分配独立 checkpoint。
func startReactionOutboxRelay(
	ctx context.Context,
	reader reactionports.OutboxReader,
	checkpoints reactionports.ProjectionCheckpointStore,
	publisher reactionports.OutboxPublisher,
	consumer string,
	healthName string,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) *reactionapp.OutboxRelay {
	relay := reactionapp.NewOutboxRelay(reader, checkpoints, publisher, consumer)
	go func() {
		if err := relay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			logger.Error("ContentReaction outbox relay stopped", "consumer", consumer, "error", err)
		}
	}()
	healthChecker.Register(healthName, func(_ context.Context) error {
		return relay.Healthy(5 * time.Second)
	})
	return relay
}

// startModerationOutboxRelay 为 PostModerationCase 事实分配独立 consumer checkpoint。
func startModerationOutboxRelay(
	ctx context.Context,
	reader moderationports.OutboxReader,
	checkpoints moderationports.ProjectionCheckpointStore,
	publisher moderationports.OutboxPublisher,
	consumer string,
	healthName string,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) *moderationapp.OutboxRelay {
	relay := moderationapp.NewOutboxRelay(reader, checkpoints, publisher, consumer)
	go func() {
		if err := relay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			logger.Error("PostModerationCase outbox relay stopped", "consumer", consumer, "error", err)
		}
	}()
	healthChecker.Register(healthName, func(_ context.Context) error {
		return relay.Healthy(5 * time.Second)
	})
	return relay
}

// startReportOutboxRelay connects the PostgreSQL aggregate/outbox transaction
// to the shared runtime event transport. Report commands never publish facts
// directly from the request transaction.
func startReportOutboxRelay(
	ctx context.Context,
	reader reportports.OutboxReader,
	checkpoints reportports.ProjectionCheckpointStore,
	publisher reportports.OutboxPublisher,
	consumer string,
	healthName string,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) *reportapp.OutboxRelay {
	relay := reportapp.NewOutboxRelay(reader, checkpoints, publisher, consumer)
	go func() {
		if err := relay.Run(ctx, 250*time.Millisecond); err != nil && ctx.Err() == nil {
			logger.Error("content report outbox relay stopped", "consumer", consumer, "error", err)
		}
	}()
	healthChecker.Register(healthName, func(_ context.Context) error {
		return relay.Healthy(5 * time.Second)
	})
	return relay
}
