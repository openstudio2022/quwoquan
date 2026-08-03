package scheduling

import (
	"context"
	"errors"
	"log/slog"
	"time"

	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

type SkillSubscriptionCronTicker interface {
	TickSkillSubscriptionCron(
		context.Context,
		skillmodel.SkillSubscriptionCronTickInput,
	) (skillmodel.SkillSubscriptionCronTickResult, error)
}

type SkillSubscriptionScheduler struct {
	ticker   SkillSubscriptionCronTicker
	interval time.Duration
	logger   *slog.Logger
}

func NewSkillSubscriptionScheduler(
	ticker SkillSubscriptionCronTicker,
	interval time.Duration,
	logger *slog.Logger,
) (*SkillSubscriptionScheduler, error) {
	if ticker == nil {
		return nil, errors.New("skill subscription cron ticker is required")
	}
	if interval <= 0 {
		return nil, errors.New("skill subscription cron interval must be positive")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &SkillSubscriptionScheduler{
		ticker:   ticker,
		interval: interval,
		logger:   logger,
	}, nil
}

func (s *SkillSubscriptionScheduler) Run(ctx context.Context) {
	s.runOnceAndObserve(ctx)
	ticker := time.NewTicker(s.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			s.runOnceAndObserve(ctx)
		}
	}
}

func (s *SkillSubscriptionScheduler) RunOnce(ctx context.Context) error {
	_, err := s.ticker.TickSkillSubscriptionCron(
		ctx,
		skillmodel.SkillSubscriptionCronTickInput{},
	)
	return err
}

func (s *SkillSubscriptionScheduler) runOnceAndObserve(ctx context.Context) {
	if err := s.RunOnce(ctx); err != nil {
		s.logger.ErrorContext(
			ctx,
			"assistant skill subscription scheduler tick failed",
			slog.String("error", err.Error()),
		)
	}
}
