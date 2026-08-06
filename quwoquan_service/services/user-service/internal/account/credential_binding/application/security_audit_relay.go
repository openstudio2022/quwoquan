package credential_binding

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
)

const credentialAuditLease = 30 * time.Second

// SecurityAuditPublisher 把脱敏 CredentialBinding 事实追加到受保留审计流。
// 它是基础设施 archive sink，不是领域 lifecycle consumer。
type SecurityAuditPublisher interface {
	PublishCredentialAudit(context.Context, bindingports.SecurityAuditEvent) error
}

type SecurityAuditRelay struct {
	outbox    bindingports.SecurityAuditOutbox
	publisher SecurityAuditPublisher
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewSecurityAuditRelay(
	outbox bindingports.SecurityAuditOutbox,
	publisher SecurityAuditPublisher,
) (*SecurityAuditRelay, error) {
	if outbox == nil || publisher == nil {
		return nil, errors.New("CredentialBinding audit outbox and publisher are required")
	}
	return &SecurityAuditRelay{outbox: outbox, publisher: publisher, now: time.Now}, nil
}

// Drain 完成 read -> durable append -> checkpoint 闭环。只有 durable transport
// 确认后才推进 published_at；失败记录摘要并等待下一次租约，绝不记录原始凭证。
func (relay *SecurityAuditRelay) Drain(ctx context.Context, limit int) (int, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	published := 0
	for published < limit {
		now := relay.now().UTC()
		event, found, err := relay.outbox.ClaimPendingOutbox(
			ctx,
			now,
			credentialAuditLease,
		)
		if err != nil {
			relay.recordFailure(err)
			return published, err
		}
		if !found {
			relay.recordSuccessfulScan(now)
			return published, nil
		}
		if err := relay.publisher.PublishCredentialAudit(ctx, event); err != nil {
			wrapped := fmt.Errorf("publish CredentialBinding audit event %s: %w", event.EventID, err)
			digest := fmt.Sprintf("sha256:%x", sha256.Sum256([]byte(wrapped.Error())))
			retryErr := relay.outbox.ScheduleOutboxRetry(
				ctx,
				event.EventID,
				event.ClaimUntil,
				now.Add(credentialAuditRetryDelay(event.AttemptCount)),
				digest,
			)
			if retryErr != nil {
				wrapped = errors.Join(wrapped, retryErr)
			}
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		if err := relay.outbox.MarkOutboxPublished(
			ctx,
			event.EventID,
			event.ClaimUntil,
			relay.now().UTC(),
		); err != nil {
			wrapped := fmt.Errorf("acknowledge CredentialBinding audit event %s: %w", event.EventID, err)
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		published++
	}
	relay.recordSuccessfulScan(relay.now().UTC())
	return published, nil
}

func (relay *SecurityAuditRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := relay.Drain(ctx, 100); err != nil && ctx.Err() == nil {
			slog.ErrorContext(ctx, "CredentialBinding audit relay failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

func (relay *SecurityAuditRelay) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	relay.healthMu.RLock()
	lastScan, lastFailure := relay.lastSuccessfulScan, relay.lastFailure
	relay.healthMu.RUnlock()
	if lastFailure != nil {
		return fmt.Errorf("CredentialBinding audit relay unhealthy: %w", lastFailure)
	}
	if lastScan.IsZero() || relay.now().UTC().Sub(lastScan) > maxStaleness {
		return errors.New("CredentialBinding audit relay heartbeat is stale")
	}
	return nil
}

func credentialAuditRetryDelay(attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 6 {
		attempt = 6
	}
	return time.Second * time.Duration(1<<(attempt-1))
}

func (relay *SecurityAuditRelay) recordSuccessfulScan(at time.Time) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = at
	relay.lastFailure = nil
	relay.healthMu.Unlock()
}

func (relay *SecurityAuditRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	relay.lastFailure = err
	relay.healthMu.Unlock()
}
