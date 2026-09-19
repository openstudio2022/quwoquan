package reaction

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

const (
	PersonaLifecycleEventStream   = "events.user.personas"
	PersonaLifecycleConsumerGroup = "content-service-content-reaction-persona-lifecycle"
)

type PersonaRetiredConsumer struct {
	redis    rtredis.Client
	cleanup  LifecycleCleanupPort
	consumer string
	logger   *slog.Logger
}

func NewPersonaRetiredConsumer(redis rtredis.Client, cleanup LifecycleCleanupPort, consumer string, logger *slog.Logger) (*PersonaRetiredConsumer, error) {
	consumer = strings.TrimSpace(consumer)
	if redis == nil || cleanup == nil || consumer == "" {
		return nil, errors.New("PersonaRetired ContentReaction consumer requires redis, cleanup port, and consumer")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &PersonaRetiredConsumer{redis: redis, cleanup: cleanup, consumer: consumer, logger: logger}, nil
}

func (consumer *PersonaRetiredConsumer) EnsureGroup(ctx context.Context) error {
	return consumer.redis.XGroupCreateMkStream(ctx, PersonaLifecycleEventStream, PersonaLifecycleConsumerGroup, "0")
}

func (consumer *PersonaRetiredConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if err := consumer.EnsureGroup(ctx); err != nil {
		return 0, err
	}
	claimed, _, err := consumer.redis.XAutoClaim(ctx, PersonaLifecycleEventStream, PersonaLifecycleConsumerGroup, consumer.consumer, 30*time.Second, "0-0", 20)
	if err != nil {
		return 0, err
	}
	fresh, err := consumer.redis.XReadGroup(ctx, PersonaLifecycleConsumerGroup, consumer.consumer, map[string]string{PersonaLifecycleEventStream: ">"}, 20, 100*time.Millisecond)
	if err != nil {
		return 0, err
	}
	messages := make([]rtredis.StreamMessage, 0, len(claimed)+len(fresh))
	seen := make(map[string]struct{}, len(claimed)+len(fresh))
	for _, group := range [][]rtredis.StreamMessage{claimed, fresh} {
		for _, message := range group {
			if _, exists := seen[message.ID]; exists {
				continue
			}
			seen[message.ID] = struct{}{}
			messages = append(messages, message)
		}
	}
	processed := 0
	for _, message := range messages {
		if strings.TrimSpace(message.Values["eventName"]) != "PersonaRetired" {
			if err := consumer.redis.XAck(ctx, PersonaLifecycleEventStream, PersonaLifecycleConsumerGroup, message.ID); err != nil {
				return processed, err
			}
			processed++
			continue
		}
		personaID, sourceVersion, eventID, occurredAt, err := decodePersonaRetired(message)
		if err != nil {
			return processed, err
		}
		actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, personaID)
		if err != nil {
			return processed, err
		}
		if err := consumer.cleanup.CleanupActor(ctx, actor, LifecycleCleanupAuthorization{
			Source: "PersonaRetired", SourceEventID: eventID, SourceVersion: sourceVersion,
			Tombstone: fmt.Sprintf("persona:%s:v%d", personaID, sourceVersion), OccurredAt: occurredAt,
		}); err != nil {
			return processed, err
		}
		if err := consumer.redis.XAck(ctx, PersonaLifecycleEventStream, PersonaLifecycleConsumerGroup, message.ID); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}

func (consumer *PersonaRetiredConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		if _, err := consumer.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			consumer.logger.ErrorContext(ctx, "PersonaRetired ContentReaction cleanup failed", "error", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func decodePersonaRetired(message rtredis.StreamMessage) (string, int64, string, time.Time, error) {
	eventID := strings.TrimSpace(message.Values["eventId"])
	personaID := strings.TrimSpace(message.Values["personaId"])
	version, err := strconv.ParseInt(strings.TrimSpace(message.Values["personaVersion"]), 10, 64)
	if err != nil || version <= 0 {
		return "", 0, "", time.Time{}, errors.New("PersonaRetired personaVersion is invalid")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(message.Values["occurredAt"]))
	if err != nil {
		return "", 0, "", time.Time{}, errors.New("PersonaRetired occurredAt is invalid")
	}
	var payload struct {
		PersonaID string `json:"personaId"`
		UserID    string `json:"userId"`
	}
	if err := json.Unmarshal([]byte(message.Values["payload"]), &payload); err != nil {
		return "", 0, "", time.Time{}, errors.New("PersonaRetired payload is invalid")
	}
	if eventID == "" || personaID == "" || payload.PersonaID != personaID || strings.TrimSpace(payload.UserID) == "" {
		return "", 0, "", time.Time{}, errors.New("PersonaRetired identity is incomplete")
	}
	return personaID, version, eventID, occurredAt.UTC(), nil
}
