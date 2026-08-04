package scheduling

import (
	"context"
	"errors"
	"log/slog"
	"sync"
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
	now      func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulTick time.Time
	lastFailure        error
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
		now:      time.Now,
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

func (s *SkillSubscriptionScheduler) RunOnce(
	ctx context.Context,
) (resultErr error) {
	defer func() {
		s.recordTick(resultErr)
	}()
	_, err := s.ticker.TickSkillSubscriptionCron(
		ctx,
		skillmodel.SkillSubscriptionCronTickInput{},
	)
	return err
}

func (s *SkillSubscriptionScheduler) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if s == nil {
		return errors.New("skill subscription scheduler is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 2 * time.Minute
	}
	s.healthMu.RLock()
	lastSuccessfulTick := s.lastSuccessfulTick
	lastFailure := s.lastFailure
	s.healthMu.RUnlock()
	if lastFailure != nil {
		return lastFailure
	}
	if lastSuccessfulTick.IsZero() {
		return errors.New("skill subscription scheduler has not completed a tick")
	}
	if s.now().UTC().Sub(lastSuccessfulTick) > maxStaleness {
		return errors.New("skill subscription scheduler heartbeat is stale")
	}
	return nil
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

func (s *SkillSubscriptionScheduler) recordTick(err error) {
	s.healthMu.Lock()
	defer s.healthMu.Unlock()
	if err != nil {
		s.lastFailure = err
		return
	}
	s.lastSuccessfulTick = s.now().UTC()
	s.lastFailure = nil
}
