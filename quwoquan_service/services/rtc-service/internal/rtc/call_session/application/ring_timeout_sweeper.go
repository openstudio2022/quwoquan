package application

import (
	"context"
	"fmt"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/event"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

const (
	ringTimeoutSystemActor = "system:rtc-ring-timeout-sweeper"
	ringTimeoutCommandName = "RingTimeout"
)

// SweepRingTimeouts 把振铃超期的会话迁移到 ended/no_answer 并经 outbox 下发
// call.ended 事实（被叫撤来电面板、双端记未接）。系统命令使用确定性幂等 key；
// named query 只返回达到 typed domain policy 阈值的候选，命令仍经共享
// mutate/CAS/receipt/outbox 管道重新加载并调用领域 HandleTimeout。
func (o *CallOrchestrator) SweepRingTimeouts(ctx context.Context) (int, error) {
	now := o.now().UTC()
	policy := o.domainService.RingTimeoutPolicy()
	sessions, err := o.repo.FindOverdueRingingCalls(
		ctx,
		now.Add(-policy.OneToOne()),
		now.Add(-policy.Group()),
		100,
	)
	if err != nil {
		return 0, fmt.Errorf("find overdue ringing calls: %w", err)
	}
	swept := 0
	for _, candidate := range sessions {
		if candidate == nil {
			continue
		}
		outcome, commandErr := o.timeoutRingingCall(ctx, candidate.ID, now)
		if commandErr != nil {
			return swept, fmt.Errorf("timeout ringing call %s: %w", candidate.ID, commandErr)
		}
		if outcome.Changed {
			swept++
		}
	}
	return swept, nil
}

func (o *CallOrchestrator) timeoutRingingCall(
	ctx context.Context,
	callID string,
	now time.Time,
) (mutationOutcome, error) {
	return o.mutateCommand(ctx, callID, mutationCommand{
		actorID:            ringTimeoutSystemActor,
		idempotencyKey:     ringTimeoutIdempotencyKey(callID),
		commandName:        ringTimeoutCommandName,
		digest:             commandDigest(ringTimeoutCommandName, callID),
		requireParticipant: false,
	}, func(session *model.CallSession) (string, CallEventPayload, error) {
		timedOut, err := o.domainService.HandleTimeout(session, now)
		if err != nil {
			return "", CallEventPayload{}, err
		}
		if !timedOut {
			return "", CallEventPayload{}, errNoop
		}
		return event.CallEnded, CallEventPayload{EndReason: session.EndReason}, nil
	})
}

// RunRingTimeoutSweeper 以固定间隔运行振铃超时收割（composition root 启动）。
func (o *CallOrchestrator) RunRingTimeoutSweeper(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		return fmt.Errorf("ring timeout sweep interval must be positive")
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		default:
		}
		if _, err := o.SweepRingTimeouts(ctx); err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

func ringTimeoutIdempotencyKey(callID string) string {
	return "rtc-call:ring-timeout:" + commandDigest(
		ringTimeoutSystemActor,
		fmt.Sprintf("%s:%s", ringTimeoutCommandName, callID),
	)
}
