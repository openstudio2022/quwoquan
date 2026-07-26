package governance_test

import (
	"context"
	"errors"
	"fmt"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/governance"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func TestRedisPublicationRateGateIsPersonaScopedAndIntentIdempotent(
	t *testing.T,
) {
	gate := NewRedisPublicationRateGate(rtredis.NewMemoryClient())
	now := time.Date(2026, 7, 20, 7, 0, 0, 0, time.UTC)
	for index := 0; index < contentgenerated.PostPublicationPersonaMaxPublications; index++ {
		decision, err := gate.AdmitPublication(
			context.Background(),
			postports.PublicationRateRequest{
				PersonaID:       "persona-a",
				PublishIntentID: fmt.Sprintf("intent-%d", index),
				OccurredAt:      now,
			},
		)
		if err != nil || !decision.Allowed {
			t.Fatalf("admission %d must pass: decision=%+v err=%v", index, decision, err)
		}
	}
	limited, err := gate.AdmitPublication(
		context.Background(),
		postports.PublicationRateRequest{
			PersonaID:       "persona-a",
			PublishIntentID: "intent-over-limit",
			OccurredAt:      now,
		},
	)
	if err != nil || limited.Allowed || limited.RetryAfter <= 0 {
		t.Fatalf("over-limit admission mismatch: decision=%+v err=%v", limited, err)
	}
	replayed, err := gate.AdmitPublication(
		context.Background(),
		postports.PublicationRateRequest{
			PersonaID:       "persona-a",
			PublishIntentID: "intent-0",
			OccurredAt:      now,
		},
	)
	if err != nil || !replayed.Allowed {
		t.Fatalf("same intent must replay prior allow: decision=%+v err=%v", replayed, err)
	}
	otherPersona, err := gate.AdmitPublication(
		context.Background(),
		postports.PublicationRateRequest{
			PersonaID:       "persona-b",
			PublishIntentID: "intent-0",
			OccurredAt:      now,
		},
	)
	if err != nil || !otherPersona.Allowed {
		t.Fatalf("another persona must have its own window: %+v err=%v", otherPersona, err)
	}
}

type failingPublicationRateRedis struct {
	rtredis.Client
}

func (failingPublicationRateRedis) SetNX(
	context.Context,
	string,
	string,
	time.Duration,
) (bool, error) {
	return false, errors.New("redis unavailable")
}

func TestRedisPublicationRateGateFailsClosedOnRedisError(t *testing.T) {
	gate := NewRedisPublicationRateGate(failingPublicationRateRedis{
		Client: rtredis.NewMemoryClient(),
	})
	decision, err := gate.AdmitPublication(
		context.Background(),
		postports.PublicationRateRequest{
			PersonaID:       "persona-a",
			PublishIntentID: "intent-a",
			OccurredAt:      time.Now(),
		},
	)
	if err == nil || decision.Allowed {
		t.Fatalf("Redis failure must fail closed: decision=%+v err=%v", decision, err)
	}
}
