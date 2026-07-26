package profileinteraction

import (
	"context"
	"encoding/json"
	"strings"
	"time"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	activityports "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/ports"
	readfactmodel "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/domain/model"
	readfactports "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/domain/ports"
)

type AppendReadFactCommand struct {
	OwnerPersonaID string
	ActivityID     string
	State          string
}

type ReadFactAck struct {
	FactID     string    `json:"factId"`
	ActivityID string    `json:"activityId"`
	State      string    `json:"state"`
	OccurredAt time.Time `json:"occurredAt"`
	Replayed   bool      `json:"replayed"`
}

type ReadFactAppendFacade interface {
	AppendReadFact(context.Context, AppendReadFactCommand) (ReadFactAck, error)
}

type ReadFactService struct {
	targets activityports.ActivityReader
	sink    readfactports.AppendSink
	now     func() time.Time
}

func NewReadFactService(
	targets activityports.ActivityReader,
	sink readfactports.AppendSink,
) *ReadFactService {
	if targets == nil || sink == nil {
		panic("ProfileInteractionReadFact service requires target reader and append sink")
	}
	return &ReadFactService{targets: targets, sink: sink, now: time.Now}
}

func (s *ReadFactService) AppendReadFact(
	ctx context.Context,
	command AppendReadFactCommand,
) (ReadFactAck, error) {
	if strings.TrimSpace(commandmeta.IdempotencyKey(ctx)) == "" {
		return ReadFactAck{}, contentgenerated.AppErrorFromIdempotencyConflict(
			"UpdateProfileInteractionState requires Idempotency-Key",
		)
	}
	fact, err := readfactmodel.New(
		command.OwnerPersonaID,
		command.ActivityID,
		command.State,
		s.now().UTC(),
	)
	if err != nil {
		return ReadFactAck{}, contentgenerated.AppErrorFromInvalidArgument(err.Error())
	}
	allowed, err := s.targets.CanAppendReadFact(
		ctx,
		fact.OwnerPersonaID,
		fact.ActivityID,
	)
	if err != nil {
		return ReadFactAck{}, contentgenerated.AppErrorFromInteractionReadModelUnavailable(
			"validate profile interaction read target: " + err.Error(),
		)
	}
	if !allowed {
		return ReadFactAck{}, contentgenerated.AppErrorFromInteractionOwnerForbidden(
			"profile interaction activity is absent, inactive, or not received by owner",
		)
	}
	payload, err := json.Marshal(fact)
	if err != nil {
		return ReadFactAck{}, contentgenerated.AppErrorFromStorageWriteFailed(err.Error())
	}
	result, err := s.sink.Append(ctx, readfactports.AppendRequest{
		Fact: fact,
		Outbox: readfactports.OutboxEvent{
			EventID:    fact.FactID,
			EventType:  readfactports.EventTypeProfileInteractionReadFactAppended,
			Payload:    payload,
			OccurredAt: fact.OccurredAt,
		},
	})
	if err != nil {
		return ReadFactAck{}, contentgenerated.AppErrorFromStorageWriteFailed(
			"append ProfileInteractionReadFact: " + err.Error(),
		)
	}
	return ReadFactAck{
		FactID:     result.Fact.FactID,
		ActivityID: result.Fact.ActivityID,
		State:      result.Fact.State,
		OccurredAt: result.Fact.OccurredAt,
		Replayed:   result.Replayed,
	}, nil
}
