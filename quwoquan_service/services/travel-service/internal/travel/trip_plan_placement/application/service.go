package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/ports"
)

type Service struct {
	store       ports.Store
	trips       ports.TripAuthority
	memberships ports.MembershipAuthority
	surfaces    ports.SurfaceAuthority
	ids         ports.IDGenerator
	now         func() time.Time
}

func NewService(
	store ports.Store,
	trips ports.TripAuthority,
	memberships ports.MembershipAuthority,
	surfaces ports.SurfaceAuthority,
	ids ports.IDGenerator,
	now func() time.Time,
) *Service {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{
		store: store, trips: trips, memberships: memberships, surfaces: surfaces, ids: ids, now: now,
	}
}

type PutCommand struct {
	ActorPersonaID  string
	IdempotencyKey  string
	TripID          string
	SurfaceKind     model.SurfaceKind
	SurfaceID       string
	SourceVersion   int64
	ExpectedVersion int64
}

type RemoveCommand struct {
	ActorPersonaID  string
	IdempotencyKey  string
	TripID          string
	SurfaceKind     model.SurfaceKind
	SurfaceID       string
	SourceVersion   int64
	ExpectedVersion int64
}

func (service *Service) Put(ctx context.Context, command PutCommand) (ports.CommandResult, error) {
	if err := service.ready(
		command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.SurfaceID,
	); err != nil || !command.SurfaceKind.Valid() || command.SourceVersion <= 0 || command.ExpectedVersion < 0 {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	if err := service.requireOrganizerAndSurfaceAdmin(ctx, command); err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	existing, getErr := service.store.Get(ctx, command.TripID, command.SurfaceKind, command.SurfaceID)
	var placement model.Placement
	var expectedVersion int64
	var err error
	switch {
	case errors.Is(getErr, ports.ErrNotFound):
		if command.ExpectedVersion != 0 {
			return ports.CommandResult{}, model.ErrRevisionConflict
		}
		placementID, idErr := service.ids.NewTripPlanPlacementID()
		if idErr != nil {
			return ports.CommandResult{}, idErr
		}
		placement, err = model.Create(model.CreateInput{
			PlacementID: placementID, TripID: command.TripID, SurfaceKind: command.SurfaceKind,
			SurfaceID: command.SurfaceID, SourceVersion: command.SourceVersion,
			CreatedByPersonaID: command.ActorPersonaID, Now: now,
		})
	case getErr != nil:
		return ports.CommandResult{}, getErr
	default:
		expectedVersion = existing.Version
		placement, err = existing.Put(command.ExpectedVersion, command.SourceVersion, now)
	}
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, expectedVersion, placement, now)
}

func (service *Service) Remove(ctx context.Context, command RemoveCommand) (ports.CommandResult, error) {
	if err := service.ready(
		command.ActorPersonaID, command.IdempotencyKey, command.TripID, command.SurfaceID,
	); err != nil || !command.SurfaceKind.Valid() || command.SourceVersion <= 0 || command.ExpectedVersion <= 0 {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	if err := service.requireOrganizerAndSurfaceAdmin(ctx, PutCommand{
		ActorPersonaID: command.ActorPersonaID, TripID: command.TripID,
		SurfaceKind: command.SurfaceKind, SurfaceID: command.SurfaceID, SourceVersion: command.SourceVersion,
	}); err != nil {
		return ports.CommandResult{}, err
	}
	placement, err := service.store.Get(ctx, command.TripID, command.SurfaceKind, command.SurfaceID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	now := service.now().UTC()
	next, err := placement.Remove(command.ExpectedVersion, command.SourceVersion, now)
	if err != nil {
		return ports.CommandResult{}, err
	}
	return service.persist(ctx, command.IdempotencyKey, digest, placement.Version, next, now)
}

func (service *Service) ListByTrip(
	ctx context.Context,
	actorPersonaID string,
	tripID string,
) ([]model.Placement, error) {
	if service == nil || service.store == nil || service.memberships == nil {
		return nil, model.ErrInvalidArgument
	}
	if err := service.memberships.CanViewTrip(ctx, strings.TrimSpace(actorPersonaID), strings.TrimSpace(tripID)); err != nil {
		return nil, err
	}
	return service.store.ListByTrip(ctx, strings.TrimSpace(tripID))
}

func (service *Service) ListBySurface(
	ctx context.Context,
	actorPersonaID string,
	kind model.SurfaceKind,
	surfaceID string,
) ([]model.Placement, error) {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	surfaceID = strings.TrimSpace(surfaceID)
	if service == nil || service.store == nil || service.surfaces == nil || actorPersonaID == "" ||
		!kind.Valid() || surfaceID == "" {
		return nil, model.ErrInvalidArgument
	}
	if err := service.surfaces.RequireMember(ctx, kind, surfaceID, actorPersonaID); err != nil {
		return nil, err
	}
	return service.store.ListActiveBySurface(ctx, kind, surfaceID)
}

func (service *Service) requireOrganizerAndSurfaceAdmin(ctx context.Context, command PutCommand) error {
	organizerID, err := service.trips.OrganizerPersonaID(ctx, strings.TrimSpace(command.TripID))
	if err != nil {
		return err
	}
	if strings.TrimSpace(command.ActorPersonaID) != strings.TrimSpace(organizerID) {
		return model.ErrPermissionDenied
	}
	return service.surfaces.RequireAdmin(
		ctx, command.SurfaceKind, strings.TrimSpace(command.SurfaceID),
		strings.TrimSpace(command.ActorPersonaID), command.SourceVersion,
	)
}

func (service *Service) ready(values ...string) error {
	if service == nil || service.store == nil || service.trips == nil || service.memberships == nil ||
		service.surfaces == nil || service.ids == nil {
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
	placement model.Placement,
	now time.Time,
) (ports.CommandResult, error) {
	eventID, err := service.ids.NewEventID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := ports.CommandResult{Placement: placement}
	commit := ports.Commit{
		ExpectedVersion: expectedVersion,
		Placement:       placement,
		Receipt: ports.Receipt{
			IdempotencyKey: key, CommandDigest: digest, Result: result,
			ExpiresAt: now.Add(7 * 24 * time.Hour),
		},
		Event: ports.OutboxEvent{
			EventID: eventID, EventType: "TripPlanPlacementChanged", AggregateID: placement.PlacementID,
			AggregateVersion: placement.Version, OccurredAt: now,
			Payload: map[string]any{
				"placementId": placement.PlacementID, "tripId": placement.TripID,
				"surfaceKind": placement.SurfaceKind, "surfaceId": placement.SurfaceID,
				"version": placement.Version, "sourceVersion": placement.SourceVersion,
				"status": placement.Status,
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
