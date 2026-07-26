// spec_ref: specs/feature-tree/runtime/runtime-assistant/proactive-subscription-delivery/spec.md#gwt-001
package local_contract

import (
	"context"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/scheduling"
)

type recordingSkillSubscriptionCronTicker struct {
	calls  atomic.Int32
	cancel context.CancelFunc
}

func (f *recordingSkillSubscriptionCronTicker) TickSkillSubscriptionCron(
	context.Context,
	assistant.SkillSubscriptionCronTickInput,
) (assistant.SkillSubscriptionCronTickResult, error) {
	if f.calls.Add(1) >= 2 {
		f.cancel()
	}
	return assistant.SkillSubscriptionCronTickResult{}, nil
}

func TestSkillSubscriptionSchedulerTicksImmediatelyAndContinues(
	t *testing.T,
) {
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	ticker := &recordingSkillSubscriptionCronTicker{cancel: cancel}
	scheduler, err := scheduling.NewSkillSubscriptionScheduler(
		ticker,
		time.Millisecond,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	go func() {
		defer close(done)
		scheduler.Run(ctx)
	}()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("订阅调度器未持续执行")
	}
	if calls := ticker.calls.Load(); calls < 2 {
		t.Fatalf("订阅调度次数=%d，至少应立即执行并周期执行各一次", calls)
	}
}

func TestSkillSubscriptionSchedulerRejectsMissingRuntimeInputs(
	t *testing.T,
) {
	if _, err := scheduling.NewSkillSubscriptionScheduler(
		nil,
		time.Minute,
		nil,
	); err == nil {
		t.Fatal("缺少订阅 tick 服务时必须 fail-fast")
	}
	ticker := &recordingSkillSubscriptionCronTicker{}
	if _, err := scheduling.NewSkillSubscriptionScheduler(
		ticker,
		0,
		nil,
	); err == nil {
		t.Fatal("非法调度周期必须 fail-fast")
	}
}
