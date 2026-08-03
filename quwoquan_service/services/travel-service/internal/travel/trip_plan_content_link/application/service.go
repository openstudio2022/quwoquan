package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/ports"
)

type Service struct {
	store       ports.Store
	memberships ports.MembershipAuthority
	trips       ports.TripAuthority
	assignments ports.AssignmentAuthority
	posts       ports.PostAuthority
	ids         ports.IDGenerator
	now         func() time.Time
}

func NewService(
	store ports.Store,
	memberships ports.MembershipAuthority,
	trips ports.TripAuthority,
	assignments ports.AssignmentAuthority,
	posts ports.PostAuthority,
	ids ports.IDGenerator,
	now func() time.Time,
) *Service {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{
		store: store, memberships: memberships, trips: trips,
		assignments: assignments, posts: posts, ids: ids, now: now,
	}
}

type PutCommand struct {
	ActorPersonaID  string
	IdempotencyKey  string
	TripID          string
	PostID          string
	ExpectedVersion int64
	RevisionNumber  int64
	TargetKind      model.TargetKind
	DayIndex        *int
	ItemID          string
	Visibility      model.Visibility
	SourceVersion   int64
}

type RemoveCommand struct {
	ActorPersonaID  string
	IdempotencyKey  string
	TripID          string
	PostID          string
	ExpectedVersion int64
	Reason          string
}

func (service *Service) Put(ctx context.Context, command PutCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.PostID); err != nil ||
		command.ExpectedVersion < 0 || command.RevisionNumber <= 0 || !command.TargetKind.Valid() ||
		!command.Visibility.Valid() || command.SourceVersion < 0 {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	if err := service.memberships.CanViewTrip(ctx, command.ActorPersonaID, command.TripID); err != nil {
		return ports.CommandResult{}, err
	}
	if command.TargetKind != model.TargetTrip {
		if command.DayIndex == nil {
			return ports.CommandResult{}, model.ErrInvalidArgument
		}
		if err := service.assignments.ValidateAssignment(
			ctx, command.TripID, command.RevisionNumber, *command.DayIndex, command.ItemID,
		); err != nil {
			return ports.CommandResult{}, err
		}
	}
	if err := service.posts.ValidateVisiblePost(
		ctx, command.ActorPersonaID, command.PostID, command.Visibility,
	); err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	existing, getErr := service.store.Get(ctx, command.TripID, command.PostID)
	var link model.Link
	var expectedVersion int64
	var err error
	switch {
	case errors.Is(getErr, ports.ErrNotFound):
		if command.ExpectedVersion != 0 {
			return ports.CommandResult{}, model.ErrRevisionConflict
		}
		linkID, idErr := service.ids.NewTripPlanContentLinkID()
		if idErr != nil {
			return ports.CommandResult{}, idErr
		}
		link, err = model.Create(model.CreateInput{
			LinkID: linkID, TripID: command.TripID, PostID: command.PostID,
			RevisionNumber: command.RevisionNumber, TargetKind: command.TargetKind, DayIndex: command.DayIndex,
			ItemID: command.ItemID, Visibility: command.Visibility,
			LinkedByPersonaID: command.ActorPersonaID, SourceVersion: command.SourceVersion, Now: now,
		})
	case getErr != nil:
		return ports.CommandResult{}, getErr
	default:
		expectedVersion = existing.Version
		link, err = existing.Put(
			command.ExpectedVersion, command.RevisionNumber, command.TargetKind, command.DayIndex, command.ItemID,
			command.Visibility, command.ActorPersonaID, command.SourceVersion, now,
		)
	}
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, expectedVersion, link, now)
}

func (service *Service) Remove(ctx context.Context, command RemoveCommand) (ports.CommandResult, error) {
	if err := service.ready(command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.PostID); err != nil ||
		command.ExpectedVersion <= 0 || strings.TrimSpace(command.Reason) == "" {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	if err := service.memberships.CanViewTrip(ctx, command.ActorPersonaID, command.TripID); err != nil {
		return ports.CommandResult{}, err
	}
	link, err := service.store.Get(ctx, command.TripID, command.PostID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	organizerPersonaID, err := service.trips.OrganizerPersonaID(ctx, command.TripID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	next, err := link.Remove(
		command.ExpectedVersion, command.ActorPersonaID, organizerPersonaID, now,
	)
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, link.Version, next, now)
}

func (service *Service) List(ctx context.Context, actorPersonaID, tripID string) ([]model.Link, error) {
	if service == nil || service.store == nil || service.memberships == nil {
		return nil, model.ErrInvalidArgument
	}
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	tripID = strings.TrimSpace(tripID)
	if actorPersonaID == "" || tripID == "" {
		return nil, model.ErrInvalidArgument
	}
	if err := service.memberships.CanViewTrip(ctx, actorPersonaID, tripID); err != nil {
		return nil, err
	}
	return service.store.ListActive(ctx, tripID)
}

func (service *Service) ready(values ...string) error {
	if service == nil || service.store == nil || service.memberships == nil || service.trips == nil ||
		service.assignments == nil || service.posts == nil || service.ids == nil {
		return model.ErrInvalidArgument
	}
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			return model.ErrInvalidArgument
		}
	}
	return nil
}

func (service *Service) replay(ctx context.Context, key, digest string) (ports.CommandResult, bool, error) {
	receipt, found, err := service.store.FindReceipt(ctx, strings.TrimSpace(key))
	if err != nil || !found {
		return ports.CommandResult{}, false, err
	}
	if receipt.CommandDigest != digest {
		return ports.CommandResult{}, true, ports.ErrIdempotencyConflict
	}
	result := receipt.Result
	result.IdempotentReplay = true
	return result, true, nil
}

func (service *Service) persist(
	ctx context.Context,
	key string,
	digest string,
	expectedVersion int64,
	link model.Link,
	now time.Time,
) (ports.CommandResult, error) {
	eventID, err := service.ids.NewEventID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := ports.CommandResult{Link: link}
	commit := ports.Commit{
		ExpectedVersion: expectedVersion,
		Link:            link,
		Receipt: ports.Receipt{
			IdempotencyKey: key, CommandDigest: digest, Result: result,
			ExpiresAt: now.Add(7 * 24 * time.Hour),
		},
		Event: ports.OutboxEvent{
			EventID: eventID, EventType: "TripPlanContentLinkChanged", AggregateID: link.LinkID,
			AggregateVersion: link.Version, OccurredAt: now,
			Payload: map[string]any{
				"linkId": link.LinkID, "tripId": link.TripID, "postId": link.PostID,
				"version": link.Version, "revisionNumber": link.RevisionNumber,
				"targetKind": link.TargetKind, "dayIndex": link.DayIndex, "itemId": link.ItemID, "visibility": link.Visibility,
				"linkedByPersonaId": link.LinkedByPersonaID, "sourceVersion": link.SourceVersion,
				"status": link.Status, "updatedAt": link.UpdatedAt,
			},
		},
	}
	if err := service.store.Commit(ctx, commit); err != nil {
		if errors.Is(err, ports.ErrCommitConflict) {
			if replay, handled, replayErr := service.replay(ctx, key, digest); handled || replayErr != nil {
				return replay, replayErr
			}
			return ports.CommandResult{}, model.ErrRevisionConflict
		}
		return ports.CommandResult{}, err
	}
	return result, nil
}

func commandDigest(command any) string {
	raw, _ := json.Marshal(command)
	digest := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(digest[:])
}
