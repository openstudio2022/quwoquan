// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/scheduling"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

type schedulerHealthTicker struct {
	mu  sync.Mutex
	err error
}

func (ticker *schedulerHealthTicker) setError(err error) {
	ticker.mu.Lock()
	defer ticker.mu.Unlock()
	ticker.err = err
}

func (ticker *schedulerHealthTicker) TickSkillSubscriptionCron(
	context.Context,
	skillmodel.SkillSubscriptionCronTickInput,
) (skillmodel.SkillSubscriptionCronTickResult, error) {
	ticker.mu.Lock()
	defer ticker.mu.Unlock()
	return skillmodel.SkillSubscriptionCronTickResult{}, ticker.err
}

type switchableReadTransport struct {
	runtimemessaging.DurableDeliveryTransport

	mu      sync.Mutex
	readErr error
}

func (transport *switchableReadTransport) setReadError(err error) {
	transport.mu.Lock()
	defer transport.mu.Unlock()
	transport.readErr = err
}

func (transport *switchableReadTransport) ReadDurable(
	ctx context.Context,
	request runtimemessaging.StreamReadRequest,
) ([]runtimemessaging.StreamDelivery, error) {
	transport.mu.Lock()
	err := transport.readErr
	transport.mu.Unlock()
	if err != nil {
		return nil, err
	}
	return transport.DurableDeliveryTransport.ReadDurable(ctx, request)
}

func TestSkillSubscriptionSchedulerHealthTracksCanonicalTick(t *testing.T) {
	ticker := &schedulerHealthTicker{}
	scheduler, err := scheduling.NewSkillSubscriptionScheduler(
		ticker,
		time.Minute,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := scheduler.Healthy(t.Context(), time.Second); err == nil {
		t.Fatal("scheduler must be unhealthy before its first subscription tick")
	}
	if err := scheduler.RunOnce(t.Context()); err != nil {
		t.Fatalf("initial subscription tick: %v", err)
	}
	if err := scheduler.Healthy(t.Context(), time.Second); err != nil {
		t.Fatalf("successful subscription tick must establish liveness: %v", err)
	}

	tickErr := errors.New("subscription store unavailable")
	ticker.setError(tickErr)
	if err := scheduler.RunOnce(t.Context()); !errors.Is(err, tickErr) {
		t.Fatalf("tick error=%v want %v", err, tickErr)
	}
	if err := scheduler.Healthy(t.Context(), time.Second); !errors.Is(err, tickErr) {
		t.Fatalf("failed subscription tick must fail health, got %v", err)
	}

	ticker.setError(nil)
	if err := scheduler.RunOnce(t.Context()); err != nil {
		t.Fatalf("recovered subscription tick: %v", err)
	}
	if err := scheduler.Healthy(t.Context(), time.Second); err != nil {
		t.Fatalf("later successful subscription tick must recover health: %v", err)
	}
}

func TestAssistantMentionedConsumerHealthTracksDurablePoll(t *testing.T) {
	redis := rtredis.NewMemoryClient()
	base := assistantSessionAssistantMentionedConsumerNewTestMessageTransport(t, redis)
	transport := &switchableReadTransport{DurableDeliveryTransport: base}
	consumer := messaging.NewAssistantMentionedConsumerWithTransport(
		transport,
		&assistantSessionAssistantMentionedConsumerMentionHandlerSpy{},
		"mentioned-health-worker",
		nil,
	)
	if err := consumer.Healthy(t.Context(), time.Second); err == nil {
		t.Fatal("consumer must be unhealthy before its first durable poll")
	}
	if _, err := consumer.ProcessOnce(t.Context()); err != nil {
		t.Fatalf("initial durable poll: %v", err)
	}
	if err := consumer.Healthy(t.Context(), time.Second); err != nil {
		t.Fatalf("successful durable poll must establish liveness: %v", err)
	}

	readErr := errors.New("assistant mention stream unavailable")
	transport.setReadError(readErr)
	if _, err := consumer.ProcessOnce(t.Context()); !errors.Is(err, readErr) {
		t.Fatalf("poll error=%v want %v", err, readErr)
	}
	if err := consumer.Healthy(t.Context(), time.Second); !errors.Is(err, readErr) {
		t.Fatalf("failed durable poll must fail health, got %v", err)
	}

	transport.setReadError(nil)
	if _, err := consumer.ProcessOnce(t.Context()); err != nil {
		t.Fatalf("recovered durable poll: %v", err)
	}
	if err := consumer.Healthy(t.Context(), time.Second); err != nil {
		t.Fatalf("later successful durable poll must recover health: %v", err)
	}
}

func TestAssistantWorkerCompositionPreflightsStartsAndJoinsSingleTrack(
	t *testing.T,
) {
	root := assistantServiceRoot(t)
	composition := readAssistantWorkerSource(
		t,
		filepath.Join(root, "cmd", "api", "composition_background_workers.go"),
	)
	supervisor := readAssistantWorkerSource(
		t,
		filepath.Join(root, "cmd", "api", "composition_worker_supervisor.go"),
	)
	mainSource := readAssistantWorkerSource(
		t,
		filepath.Join(root, "cmd", "api", "main.go"),
	)
	sloSource := readAssistantWorkerSource(
		t,
		filepath.Join(
			root,
			"observability",
			"slo",
			"background_worker_supervisor_slo.yaml",
		),
	)

	if strings.Contains(composition, "go ") {
		t.Fatal("composition must not launch a worker before unified supervisor Start")
	}
	startIndex := strings.Index(composition, "workers.Start()")
	if startIndex < 0 {
		t.Fatal("composition is missing the single worker Start boundary")
	}
	for _, preflight := range []string{
		"SetDurableRetention(",
		"consumer.EnsureGroup(preflightCtx)",
		"placementConsumer.EnsureGroup(preflightCtx)",
		"newAssistantBackgroundWorkers(",
	} {
		index := strings.Index(composition, preflight)
		if index < 0 || index > startIndex {
			t.Fatalf("worker preflight %q must complete before Start", preflight)
		}
	}
	for _, healthName := range []string{
		"assistant_run_terminal_relay",
		"assistant_skill_subscription_scheduler",
		"assistant_learning_projection_scheduler",
		"assistant_learning_fact_outbox_relay",
		"assistant_policy_release_outbox_relay",
		"assistant_policy_rollout_outbox_relay",
		"assistant_mentioned_consumer",
		"assistant_membership_consumer",
		"assistant_durable_run_worker",
	} {
		if !strings.Contains(composition, healthName) {
			t.Fatalf("composition is missing real worker health %q", healthName)
		}
		if !strings.Contains(sloSource, healthName) {
			t.Fatalf("worker SLO is missing canonical health check %q", healthName)
		}
	}
	for _, required := range []string{
		"runtime_health_check_status",
		"background_worker_unhealthy",
		"cancel_sibling_workers_and_mark_readiness_unhealthy",
		"join_all_workers_before_closing_dependencies",
	} {
		if !strings.Contains(sloSource, required) {
			t.Fatalf("worker SLO is missing %q", required)
		}
	}
	for _, required := range []string{
		"workers.cancel()",
		"workers.waitGroup.Wait()",
		"<-workers.done",
		"waiting before dependency close",
	} {
		if !strings.Contains(supervisor, required) {
			t.Fatalf("worker supervisor is missing %q", required)
		}
	}
	workerCloseIndex := strings.Index(
		mainSource,
		"errors.Join(resultErr, workers.Close())",
	)
	infrastructureCloseIndex := strings.Index(
		mainSource,
		"defer infrastructure.Close()",
	)
	if workerCloseIndex < 0 || infrastructureCloseIndex < 0 ||
		workerCloseIndex < infrastructureCloseIndex {
		t.Fatal("worker join defer must be registered after dependency close defer")
	}
}

func readAssistantWorkerSource(t *testing.T, path string) string {
	t.Helper()
	contents, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(contents)
}

var _ runtimemessaging.DurableDeliveryTransport = (*switchableReadTransport)(nil)
