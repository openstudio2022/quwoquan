// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	placementmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/messaging"
)

type membershipSwitchableReadTransport struct {
	runtimemessaging.DurableDeliveryTransport

	mu      sync.Mutex
	readErr error
}

func (transport *membershipSwitchableReadTransport) setReadError(err error) {
	transport.mu.Lock()
	defer transport.mu.Unlock()
	transport.readErr = err
}

func (transport *membershipSwitchableReadTransport) ReadDurable(
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

func TestAssistantMembershipConsumerHealthTracksDurablePoll(t *testing.T) {
	redis := rtredis.NewMemoryClient()
	base, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"assistant-service-test",
		runtimemessaging.RedisMessageTransportFixture,
		redis,
		redis,
	)
	if err != nil {
		t.Fatal(err)
	}
	transport := &membershipSwitchableReadTransport{
		DurableDeliveryTransport: base,
	}
	consumer := placementmessaging.NewAssistantMembershipConsumer(
		transport,
		application.NewMembershipProjector(&placementStore{}, nil),
		"membership-health-worker",
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

	readErr := errors.New("assistant membership stream unavailable")
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

var _ runtimemessaging.DurableDeliveryTransport = (*membershipSwitchableReadTransport)(nil)
