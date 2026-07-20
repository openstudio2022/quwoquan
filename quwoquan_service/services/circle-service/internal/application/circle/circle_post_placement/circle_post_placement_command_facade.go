package circlepostplacement

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	placementmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/model"
	placementports "quwoquan_service/services/circle-service/internal/domain/circle/circle_post_placement/ports"
	generated "quwoquan_service/services/circle-service/internal/generated"
)

const placementReceiptRetention = 7 * 24 * time.Hour

type PlaceCommand struct {
	CircleID string
	PostID   string
	GroupID  string
}

type TargetCommand struct {
	CircleID    string
	PlacementID string
}

type PresentationCommand struct {
	CircleID    string
	PlacementID string
	Enabled     bool
}

type CommandResult struct {
	PlacementID      string `json:"placementId"`
	Version          int64  `json:"version"`
	State            string `json:"state"`
	IdempotentReplay bool   `json:"idempotentReplay"`
}

type CommandFacade struct {
	store   placementports.AggregateStore
	readers placementports.PolicyReaders
	now     func() time.Time
}

func NewCommandFacade(store placementports.AggregateStore, readers placementports.PolicyReaders) *CommandFacade {
	if store == nil || readers.Circles == nil || readers.Groups == nil ||
		readers.Posts == nil || readers.Memberships == nil {
		panic("CirclePostPlacement CommandFacade requires Store and all named policy Readers")
	}
	return &CommandFacade{store: store, readers: readers, now: time.Now}
}

func (f *CommandFacade) Place(ctx context.Context, command PlaceCommand) (CommandResult, error) {
	command.CircleID = strings.TrimSpace(command.CircleID)
	command.PostID = strings.TrimSpace(command.PostID)
	command.GroupID = strings.TrimSpace(command.GroupID)
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil || command.CircleID == "" || command.PostID == "" {
		return CommandResult{}, generated.AppErrorFromInvalidArgument("PlacePostInCircle requires trusted persona, circleId and postId")
	}
	circle, err := f.requireActiveCircle(ctx, command.CircleID)
	if err != nil {
		return CommandResult{}, err
	}
	if command.GroupID != "" {
		group, found, readErr := f.readers.Groups.ReadGroupPolicy(ctx, command.GroupID)
		if readErr != nil {
			return CommandResult{}, generated.AppErrorFromPlacementStorageWriteFailed(readErr.Error())
		}
		if !found || group.CircleID != command.CircleID || group.State != "active" {
			return CommandResult{}, generated.AppErrorFromInvalidArgument("group does not belong to the active circle")
		}
	}
	post, found, readErr := f.readers.Posts.ReadPostOwner(ctx, command.PostID)
	if readErr != nil {
		return CommandResult{}, generated.AppErrorFromPlacementStorageWriteFailed(readErr.Error())
	}
	if !found || post.State != "published" || strings.TrimSpace(post.OwnerPersonaID) == "" {
		return CommandResult{}, generated.AppErrorFromInvalidArgument("post is not an eligible published Post projection")
	}
	moderator, err := f.isModerator(ctx, circle, actorID)
	if err != nil {
		return CommandResult{}, err
	}
	if actorID != post.OwnerPersonaID && !moderator {
		return CommandResult{}, generated.AppErrorFromPermissionDenied("actor is neither post owner nor circle moderator")
	}
	placementID := stablePlacementID(command.CircleID, actorID, current.IdempotencyKey)
	change := placementmodel.ChangeSet{
		Kind: placementmodel.ChangePlace, PlacementID: placementID, PostID: command.PostID,
		OwnerPersonaID: post.OwnerPersonaID, CircleID: command.CircleID, GroupID: command.GroupID,
		ExpectedVersion: 0, OccurredAt: f.now().UTC(),
	}
	return f.commit(ctx, current, actorID, change)
}

func (f *CommandFacade) Remove(ctx context.Context, command TargetCommand) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	placement, err := f.requirePlacement(ctx, command.CircleID, command.PlacementID)
	if err != nil {
		return CommandResult{}, err
	}
	circle, err := f.requireActiveCircle(ctx, strings.TrimSpace(command.CircleID))
	if err != nil {
		return CommandResult{}, err
	}
	moderator, err := f.isModerator(ctx, circle, actorID)
	if err != nil {
		return CommandResult{}, err
	}
	if actorID != placement.OwnerPersonaID && !moderator {
		return CommandResult{}, generated.AppErrorFromPermissionDenied("actor is neither post owner nor circle moderator")
	}
	change := placementmodel.ChangeSet{
		Kind: placementmodel.ChangeRemove, PlacementID: placement.ID, CircleID: placement.CircleID,
		ExpectedVersion: placement.Version, OccurredAt: f.now().UTC(),
	}
	if placement.State == placementmodel.CirclePostPlacementStateRemoved {
		return f.recordNoop(ctx, current, actorID, placement, change)
	}
	return f.commit(ctx, current, actorID, change)
}

func (f *CommandFacade) SetPinned(ctx context.Context, command PresentationCommand) (CommandResult, error) {
	return f.setPresentation(ctx, placementmodel.ChangePin, command)
}

func (f *CommandFacade) SetFeatured(ctx context.Context, command PresentationCommand) (CommandResult, error) {
	return f.setPresentation(ctx, placementmodel.ChangeFeature, command)
}

func (f *CommandFacade) setPresentation(ctx context.Context, kind placementmodel.ChangeKind, command PresentationCommand) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	placement, err := f.requirePlacement(ctx, command.CircleID, command.PlacementID)
	if err != nil {
		return CommandResult{}, err
	}
	circle, err := f.requireActiveCircle(ctx, placement.CircleID)
	if err != nil {
		return CommandResult{}, err
	}
	moderator, err := f.isModerator(ctx, circle, actorID)
	if err != nil {
		return CommandResult{}, err
	}
	if !moderator {
		return CommandResult{}, generated.AppErrorFromPermissionDenied("presentation changes require circle moderator")
	}
	change := placementmodel.ChangeSet{
		Kind: kind, PlacementID: placement.ID, CircleID: placement.CircleID,
		ExpectedVersion: placement.Version, Enabled: command.Enabled, OccurredAt: f.now().UTC(),
	}
	if (kind == placementmodel.ChangePin && placement.Pinned == command.Enabled) ||
		(kind == placementmodel.ChangeFeature && placement.Featured == command.Enabled) {
		return f.recordNoop(ctx, current, actorID, placement, change)
	}
	return f.commit(ctx, current, actorID, change)
}

// recordNoop 持久化"目标状态已满足"回执；首个 Idempotency-Key 也能重放原始结果。
func (f *CommandFacade) recordNoop(ctx context.Context, current operation.Context, actorID string, placement placementmodel.CirclePostPlacement, change placementmodel.ChangeSet) (CommandResult, error) {
	digest, err := commandDigest(actorID, change)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromPlacementStorageWriteFailed(err.Error())
	}
	receipt, err := f.store.RecordNoopReceipt(ctx, placementports.NoopReceipt{
		PlacementID: placement.ID, Version: placement.Version, State: placement.State,
		ReceiptKey:    scopedReceiptKey(actorID, current.IdempotencyKey),
		CommandDigest: digest, ReceiptExpiresAt: f.now().UTC().Add(placementReceiptRetention),
	})
	if err != nil {
		return CommandResult{}, mapCommitError(err)
	}
	return CommandResult{
		PlacementID: receipt.PlacementID, Version: receipt.Version,
		State: string(receipt.State), IdempotentReplay: true,
	}, nil
}

func (f *CommandFacade) requirePlacement(ctx context.Context, circleID, placementID string) (placementmodel.CirclePostPlacement, error) {
	circleID = strings.TrimSpace(circleID)
	placementID = strings.TrimSpace(placementID)
	if circleID == "" || placementID == "" {
		return placementmodel.CirclePostPlacement{}, generated.AppErrorFromInvalidArgument("circleId and placementId are required")
	}
	placement, found, err := f.store.Load(ctx, placementID)
	if err != nil {
		return placementmodel.CirclePostPlacement{}, generated.AppErrorFromPlacementStorageWriteFailed(err.Error())
	}
	if !found || placement.CircleID != circleID {
		return placementmodel.CirclePostPlacement{}, generated.AppErrorFromPlacementNotFound("placement not found in circle")
	}
	return placement, nil
}

func (f *CommandFacade) requireActiveCircle(ctx context.Context, circleID string) (placementports.CirclePolicySlice, error) {
	circle, found, err := f.readers.Circles.ReadCirclePolicy(ctx, circleID)
	if err != nil {
		return placementports.CirclePolicySlice{}, generated.AppErrorFromPlacementStorageWriteFailed(err.Error())
	}
	if !found {
		return placementports.CirclePolicySlice{}, generated.AppErrorFromCircleNotFound("placement target circle not found")
	}
	if circle.State != "active" {
		return placementports.CirclePolicySlice{}, generated.AppErrorFromInvalidArgument("placement target circle is not active")
	}
	return circle, nil
}

func (f *CommandFacade) isModerator(ctx context.Context, circle placementports.CirclePolicySlice, actorID string) (bool, error) {
	if actorID == strings.TrimSpace(circle.OwnerPersonaID) {
		return true, nil
	}
	membership, found, err := f.readers.Memberships.ReadMembershipRole(ctx, circle.CircleID, actorID)
	if err != nil {
		return false, generated.AppErrorFromPlacementStorageWriteFailed(err.Error())
	}
	if !found || membership.State != "active" {
		return false, nil
	}
	return membership.Role == "owner" || membership.Role == "admin", nil
}

func (f *CommandFacade) commit(ctx context.Context, current operation.Context, actorID string, change placementmodel.ChangeSet) (CommandResult, error) {
	digest, err := commandDigest(actorID, change)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromPlacementStorageWriteFailed(err.Error())
	}
	for attempt := 0; attempt < 3; attempt++ {
		receipt, commitErr := f.store.Commit(ctx, placementports.CommitRequest{
			Change: change, ReceiptKey: scopedReceiptKey(actorID, current.IdempotencyKey),
			CommandDigest: digest, ReceiptExpiresAt: f.now().UTC().Add(placementReceiptRetention),
		})
		if commitErr == nil {
			return CommandResult{
				PlacementID: receipt.PlacementID, Version: receipt.Version,
				State: string(receipt.State), IdempotentReplay: receipt.Replayed,
			}, nil
		}
		if change.Kind == placementmodel.ChangePlace ||
			!errors.Is(commitErr, placementmodel.ErrVersionConflict) ||
			attempt == 2 {
			return CommandResult{}, mapCommitError(commitErr)
		}
		latest, found, loadErr := f.store.Load(ctx, change.PlacementID)
		if loadErr != nil {
			return CommandResult{}, generated.AppErrorFromPlacementStorageWriteFailed(loadErr.Error())
		}
		if !found {
			return CommandResult{}, mapCommitError(placementmodel.ErrNotFound)
		}
		if transitionAlreadyApplied(latest, change) {
			return f.recordNoop(ctx, current, actorID, latest, change)
		}
		change.ExpectedVersion = latest.Version
	}
	panic("unreachable CirclePostPlacement commit retry")
}

func transitionAlreadyApplied(
	placement placementmodel.CirclePostPlacement,
	change placementmodel.ChangeSet,
) bool {
	switch change.Kind {
	case placementmodel.ChangeRemove:
		return placement.State == placementmodel.CirclePostPlacementStateRemoved
	case placementmodel.ChangePin:
		return placement.State == placementmodel.CirclePostPlacementStateActive &&
			placement.Pinned == change.Enabled
	case placementmodel.ChangeFeature:
		return placement.State == placementmodel.CirclePostPlacementStateActive &&
			placement.Featured == change.Enabled
	default:
		return false
	}
}

func commandResultFromPlacement(
	placement placementmodel.CirclePostPlacement,
	replayed bool,
) CommandResult {
	return CommandResult{
		PlacementID:      placement.ID,
		Version:          placement.Version,
		State:            string(placement.State),
		IdempotentReplay: replayed,
	}
}

func trustedCommandContext(ctx context.Context) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil ||
		strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", generated.AppErrorFromInvalidArgument("trusted persona and Idempotency-Key are required")
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func commandDigest(actorID string, change placementmodel.ChangeSet) (string, error) {
	if change.Kind != placementmodel.ChangePlace {
		change.ExpectedVersion = 0
	}
	payload, err := json.Marshal(struct {
		ActorID         string                    `json:"actorId"`
		Kind            placementmodel.ChangeKind `json:"kind"`
		PostID          string                    `json:"postId,omitempty"`
		CircleID        string                    `json:"circleId"`
		GroupID         string                    `json:"groupId,omitempty"`
		ExpectedVersion int64                     `json:"expectedVersion"`
		Enabled         bool                      `json:"enabled,omitempty"`
	}{actorID, change.Kind, change.PostID, change.CircleID, change.GroupID, change.ExpectedVersion, change.Enabled})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func scopedReceiptKey(actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return hex.EncodeToString(sum[:])
}

func stablePlacementID(circleID, actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(circleID) + "\x00" +
			strings.TrimSpace(actorID) + "\x00" +
			strings.TrimSpace(idempotencyKey),
	))
	return "cpp_" + hex.EncodeToString(sum[:16])
}

func mapCommitError(err error) error {
	switch {
	case errors.Is(err, placementmodel.ErrAlreadyExists):
		return generated.AppErrorFromPlacementAlreadyExists(err.Error())
	case errors.Is(err, placementmodel.ErrNotFound):
		return generated.AppErrorFromPlacementNotFound(err.Error())
	case errors.Is(err, placementmodel.ErrVersionConflict), errors.Is(err, placementmodel.ErrInactive):
		return generated.AppErrorFromPlacementVersionConflict(err.Error())
	case errors.Is(err, placementmodel.ErrIdempotencyConflict):
		return generated.AppErrorFromPlacementIdempotencyConflict(err.Error())
	case errors.Is(err, placementmodel.ErrInvalidChange):
		return generated.AppErrorFromInvalidArgument(err.Error())
	default:
		return generated.AppErrorFromPlacementStorageWriteFailed(err.Error())
	}
}
