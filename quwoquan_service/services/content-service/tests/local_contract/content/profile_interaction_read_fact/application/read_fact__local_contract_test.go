package application_test

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	postgenerated "quwoquan_service/services/content-service/generated/content/post"
	readfactgenerated "quwoquan_service/services/content-service/generated/content/profile_interaction_read_fact"
	"quwoquan_service/runtime/commandmeta"
	activityports "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/ports"
	readfactapp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/application"
	readfactmodel "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/domain/model"
	readfactports "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/domain/ports"
)

type targetReader struct {
	allowed bool
	err     error
}

func (r targetReader) List(
	context.Context,
	activityports.PageRequest,
) (activityports.Page, error) {
	return activityports.Page{}, nil
}

func (r targetReader) CanAppendReadFact(
	context.Context,
	string,
	string,
) (bool, error) {
	return r.allowed, r.err
}

type appendSink struct {
	request readfactports.AppendRequest
	err     error
}

func (s *appendSink) Append(
	_ context.Context,
	request readfactports.AppendRequest,
) (readfactports.AppendResult, error) {
	s.request = request
	if s.err != nil {
		return readfactports.AppendResult{}, s.err
	}
	return readfactports.AppendResult{Fact: request.Fact}, nil
}

func TestAppendReadFactRequiresIdempotencyAndOwnedActivity(t *testing.T) {
	command := readfactapp.AppendReadFactCommand{
		OwnerPersonaID: "persona-owner",
		ActivityID:     "activity-1",
		State:          readfactmodel.StateSeen,
	}

	service := readfactapp.NewReadFactService(targetReader{allowed: true}, &appendSink{})
	if _, err := service.AppendReadFact(context.Background(), command); !hasErrorCode(
		err,
		postgenerated.ErrIdempotencyConflict,
	) {
		t.Fatalf("missing idempotency key error = %v", err)
	}

	service = readfactapp.NewReadFactService(targetReader{allowed: false}, &appendSink{})
	if _, err := service.AppendReadFact(commandContext(), command); !hasErrorCode(
		err,
		readfactgenerated.ErrProfileInteractionReadFactOwnerForbidden,
	) {
		t.Fatalf("foreign or absent activity error = %v", err)
	}

	service = readfactapp.NewReadFactService(
		targetReader{err: errors.New("projection unavailable")},
		&appendSink{},
	)
	if _, err := service.AppendReadFact(commandContext(), command); !hasErrorCode(
		err,
		readfactgenerated.ErrProfileInteractionReadFactTargetUnavailable,
	) {
		t.Fatalf("projection failure error = %v", err)
	}
}

func TestAppendReadFactCommitsCanonicalFactAndOutboxEvent(t *testing.T) {
	sink := &appendSink{}
	service := readfactapp.NewReadFactService(targetReader{allowed: true}, sink)
	ack, err := service.AppendReadFact(
		commandContext(),
		readfactapp.AppendReadFactCommand{
			OwnerPersonaID: " persona-owner ",
			ActivityID:     " activity-1 ",
			State:          readfactmodel.StateRead,
		},
	)
	if err != nil {
		t.Fatalf("append read fact: %v", err)
	}
	if ack.FactID == "" || ack.ActivityID != "activity-1" ||
		ack.State != readfactmodel.StateRead || ack.OccurredAt.IsZero() {
		t.Fatalf("unexpected acknowledgement: %+v", ack)
	}
	if sink.request.Outbox.EventID != ack.FactID ||
		sink.request.Outbox.EventType != readfactports.EventTypeProfileInteractionReadFactAppended ||
		!sink.request.Outbox.OccurredAt.Equal(ack.OccurredAt) {
		t.Fatalf("outbox is not bound to canonical fact: %+v", sink.request.Outbox)
	}
	var payload readfactmodel.Fact
	if err := json.Unmarshal(sink.request.Outbox.Payload, &payload); err != nil {
		t.Fatalf("decode outbox payload: %v", err)
	}
	if payload.FactID != ack.FactID || payload.OwnerPersonaID != "persona-owner" ||
		payload.ActivityID != ack.ActivityID || payload.State != ack.State {
		t.Fatalf("outbox payload drifted from fact: %+v", payload)
	}
}

func commandContext() context.Context {
	return commandmeta.WithIdempotencyKey(context.Background(), "profile-read-fact-1")
}

func hasErrorCode(err error, code error) bool {
	return err != nil && strings.Contains(err.Error(), code.Error())
}
