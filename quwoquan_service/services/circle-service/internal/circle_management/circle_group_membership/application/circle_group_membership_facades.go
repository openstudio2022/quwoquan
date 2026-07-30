package circlegroupmembership

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	circleerrors "quwoquan_service/services/circle-service/generated/circle_management/circle"
	grouperrors "quwoquan_service/services/circle-service/generated/circle_management/circle_group"
	generated "quwoquan_service/services/circle-service/generated/circle_management/circle_group_membership"
	membershiperrors "quwoquan_service/services/circle-service/generated/circle_management/circle_membership"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/ports"
)

const receiptRetention = 7 * 24 * time.Hour

type TargetCommand struct {
	CircleID        string
	GroupID         string
	TargetPersonaID string
	Role            model.CircleGroupMembershipRole
}

type SelfCommand struct {
	CircleID string
	GroupID  string
}

type CommandResult struct {
	MembershipID     string `json:"membershipId"`
	Version          int64  `json:"version"`
	Role             string `json:"role"`
	State            string `json:"state"`
	IdempotentReplay bool   `json:"idempotentReplay"`
}

type CommandFacade struct {
	store       ports.AggregateStore
	groups      ports.GroupPolicyReader
	circles     ports.CircleMembershipPolicyReader
	memberships ports.MembershipReader
	now         func() time.Time
}

func NewCommandFacade(store ports.AggregateStore, groups ports.GroupPolicyReader, circles ports.CircleMembershipPolicyReader, memberships ports.MembershipReader) *CommandFacade {
	if store == nil || groups == nil || circles == nil || memberships == nil {
		panic("CircleGroupMembership CommandFacade requires Store and named Readers")
	}
	return &CommandFacade{store: store, groups: groups, circles: circles, memberships: memberships, now: time.Now}
}

func (facade *CommandFacade) Apply(ctx context.Context, circleID, groupID string) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	group, err := facade.requireGroup(ctx, circleID, groupID)
	if err != nil {
		return CommandResult{}, err
	}
	active, err := facade.circles.IsActiveCircleMember(ctx, group.CircleID, actorID)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	if !active {
		return CommandResult{}, membershiperrors.AppErrorFromNotMember("active Circle membership is required before joining a group")
	}
	if group.JoinPolicy == "invite_only" {
		return CommandResult{}, circleerrors.AppErrorFromPermissionDenied("invite-only CircleGroup does not accept self applications")
	}
	membershipID := stableMembershipID(group.GroupID, actorID)
	existing, found, err := facade.store.LoadByIdentity(ctx, group.GroupID, actorID)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	expectedVersion := int64(0)
	if found {
		expectedVersion = existing.Version
	}
	return facade.commit(ctx, current, model.ChangeSet{
		Kind: model.ChangeApply, MembershipID: membershipID, GroupID: group.GroupID,
		CircleID: group.CircleID, PersonaID: actorID, ActorPersonaID: actorID,
		ExpectedVersion: expectedVersion, Role: model.CircleGroupMembershipRoleMember,
		OccurredAt: facade.now().UTC(),
	})
}

// ActivateOwner is the only event-consumer entrypoint. The caller must derive
// the idempotency key from the immutable CircleGroupCreated event id.
func (facade *CommandFacade) ActivateOwner(ctx context.Context, circleID, groupID, ownerPersonaID string) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	if actorID != strings.TrimSpace(ownerPersonaID) {
		return CommandResult{}, circleerrors.AppErrorFromPermissionDenied("CircleGroupCreated owner does not match trusted persona")
	}
	group, err := facade.requireGroup(ctx, circleID, groupID)
	if err != nil {
		return CommandResult{}, err
	}
	membershipID := stableMembershipID(group.GroupID, actorID)
	existing, found, err := facade.store.LoadByIdentity(ctx, group.GroupID, actorID)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	expectedVersion := int64(0)
	if found {
		expectedVersion = existing.Version
	}
	return facade.commit(ctx, current, model.ChangeSet{
		Kind: model.ChangeActivateOwner, MembershipID: membershipID, GroupID: group.GroupID,
		CircleID: group.CircleID, PersonaID: actorID, ActorPersonaID: actorID,
		ExpectedVersion: expectedVersion, Role: model.CircleGroupMembershipRoleOwner,
		DirectActivate: true, OccurredAt: facade.now().UTC(),
	})
}

func (facade *CommandFacade) Approve(ctx context.Context, command TargetCommand) (CommandResult, error) {
	return facade.decide(ctx, command, model.ChangeApprove, false)
}

func (facade *CommandFacade) Reject(ctx context.Context, command TargetCommand) (CommandResult, error) {
	return facade.decide(ctx, command, model.ChangeReject, false)
}

func (facade *CommandFacade) Remove(ctx context.Context, command TargetCommand) (CommandResult, error) {
	return facade.decide(ctx, command, model.ChangeRemove, false)
}

func (facade *CommandFacade) UpdateRole(ctx context.Context, command TargetCommand) (CommandResult, error) {
	return facade.decide(ctx, command, model.ChangeRole, true)
}

func (facade *CommandFacade) decide(ctx context.Context, command TargetCommand, kind model.ChangeKind, ownerOnly bool) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	group, err := facade.requireGroup(ctx, command.CircleID, command.GroupID)
	if err != nil {
		return CommandResult{}, err
	}
	role, err := facade.requireManager(ctx, group.GroupID, actorID)
	if err != nil {
		return CommandResult{}, err
	}
	if ownerOnly && role != model.CircleGroupMembershipRoleOwner {
		return CommandResult{}, circleerrors.AppErrorFromPermissionDenied("only the CircleGroup owner may change roles")
	}
	targetPersonaID := strings.TrimSpace(command.TargetPersonaID)
	target, found, err := facade.store.LoadByIdentity(ctx, group.GroupID, targetPersonaID)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	if !found {
		return CommandResult{}, generated.AppErrorFromGroupMembershipNotFound("target group membership not found")
	}
	return facade.commit(ctx, current, model.ChangeSet{
		Kind: kind, MembershipID: target.ID, GroupID: target.GroupID, CircleID: target.CircleID,
		PersonaID: target.PersonaID, ActorPersonaID: actorID, ExpectedVersion: target.Version,
		Role: command.Role, OccurredAt: facade.now().UTC(),
	})
}

func (facade *CommandFacade) Leave(ctx context.Context, command SelfCommand) (CommandResult, error) {
	current, actorID, err := trustedCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	group, err := facade.requireGroup(ctx, command.CircleID, command.GroupID)
	if err != nil {
		return CommandResult{}, err
	}
	target, found, err := facade.store.LoadByIdentity(ctx, group.GroupID, actorID)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	if !found {
		return CommandResult{}, generated.AppErrorFromGroupMembershipNotFound("self group membership not found")
	}
	return facade.commit(ctx, current, model.ChangeSet{
		Kind: model.ChangeLeave, MembershipID: target.ID, GroupID: target.GroupID, CircleID: target.CircleID,
		PersonaID: target.PersonaID, ActorPersonaID: actorID, ExpectedVersion: target.Version,
		OccurredAt: facade.now().UTC(),
	})
}

func (facade *CommandFacade) requireGroup(ctx context.Context, circleID, groupID string) (ports.GroupPolicySlice, error) {
	group, found, err := facade.groups.ReadGroupPolicy(ctx, strings.TrimSpace(circleID), strings.TrimSpace(groupID))
	if err != nil {
		return ports.GroupPolicySlice{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	if !found {
		return ports.GroupPolicySlice{}, grouperrors.AppErrorFromGroupNotFound("CircleGroupMembership target group not found")
	}
	if group.Status != "active" {
		return ports.GroupPolicySlice{}, grouperrors.AppErrorFromGroupArchived("CircleGroupMembership target group is archived")
	}
	return group, nil
}

func (facade *CommandFacade) requireManager(ctx context.Context, groupID, actorID string) (model.CircleGroupMembershipRole, error) {
	membership, found, err := facade.memberships.ReadGroupMembership(ctx, groupID, actorID)
	if err != nil {
		return "", generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	if !found || membership.State != model.CircleGroupMembershipStateActive ||
		(membership.Role != model.CircleGroupMembershipRoleOwner && membership.Role != model.CircleGroupMembershipRoleManager) {
		return "", circleerrors.AppErrorFromPermissionDenied("active CircleGroup owner or manager membership is required")
	}
	return membership.Role, nil
}

func (facade *CommandFacade) commit(ctx context.Context, current operation.Context, change model.ChangeSet) (CommandResult, error) {
	digest, err := commandDigest(change)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	for attempt := 0; attempt < 3; attempt++ {
		receipt, commitErr := facade.store.Commit(ctx, ports.CommitRequest{
			Change: change, ReceiptKey: receiptKey(change.ActorPersonaID, current.IdempotencyKey),
			CommandDigest: digest, ReceiptExpiresAt: facade.now().UTC().Add(receiptRetention),
		})
		if commitErr == nil {
			return CommandResult{
				MembershipID: receipt.MembershipID, Version: receipt.Version, Role: string(receipt.Role),
				State: string(receipt.State), IdempotentReplay: receipt.Replayed,
			}, nil
		}
		if !errors.Is(commitErr, model.ErrVersionConflict) || attempt == 2 {
			return CommandResult{}, mapCommitError(commitErr)
		}
		latest, found, loadErr := facade.store.LoadByIdentity(
			ctx,
			change.GroupID,
			change.PersonaID,
		)
		if loadErr != nil {
			return CommandResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(loadErr.Error())
		}
		if !found {
			return CommandResult{}, mapCommitError(model.ErrNotFound)
		}
		change.ExpectedVersion = latest.Version
	}
	panic("unreachable CircleGroupMembership commit retry")
}

func trustedCommandContext(ctx context.Context) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil || strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", circleerrors.AppErrorFromInvalidArgument("trusted persona and Idempotency-Key are required")
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func trustedPersona(ctx context.Context) (string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return "", circleerrors.AppErrorFromInvalidArgument("trusted persona is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func commandDigest(change model.ChangeSet) (string, error) {
	payload, err := json.Marshal(struct {
		Kind           model.ChangeKind                `json:"kind"`
		MembershipID   string                          `json:"membershipId"`
		GroupID        string                          `json:"groupId"`
		CircleID       string                          `json:"circleId"`
		PersonaID      string                          `json:"personaId"`
		ActorPersonaID string                          `json:"actorPersonaId"`
		Role           model.CircleGroupMembershipRole `json:"role"`
		DirectActivate bool                            `json:"directActivate"`
	}{change.Kind, change.MembershipID, change.GroupID, change.CircleID, change.PersonaID, change.ActorPersonaID, change.Role, change.DirectActivate})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func receiptKey(actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return hex.EncodeToString(sum[:])
}

func stableMembershipID(groupID, personaID string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(groupID) + "\x00" + strings.TrimSpace(personaID)))
	return "cgm_" + hex.EncodeToString(sum[:16])
}

func mapCommitError(err error) error {
	switch {
	case errors.Is(err, model.ErrAlreadyActive):
		return generated.AppErrorFromGroupMembershipAlreadyActive(err.Error())
	case errors.Is(err, model.ErrGroupFull):
		return generated.AppErrorFromGroupMembershipFull(err.Error())
	case errors.Is(err, model.ErrNotFound):
		return generated.AppErrorFromGroupMembershipNotFound(err.Error())
	case errors.Is(err, model.ErrStateConflict):
		return generated.AppErrorFromGroupMembershipStateConflict(err.Error())
	case errors.Is(err, model.ErrOwnerCannotLeave):
		return generated.AppErrorFromGroupMembershipOwnerCannotLeave(err.Error())
	case errors.Is(err, model.ErrOwnerCannotRemove):
		return generated.AppErrorFromGroupMembershipOwnerCannotRemove(err.Error())
	case errors.Is(err, model.ErrInvalidRole):
		return generated.AppErrorFromGroupMembershipRoleInvalid(err.Error())
	case errors.Is(err, model.ErrVersionConflict):
		return generated.AppErrorFromGroupMembershipVersionConflict(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return generated.AppErrorFromGroupMembershipIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrInvalidChange):
		return circleerrors.AppErrorFromInvalidArgument(err.Error())
	default:
		return generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
}

type MembershipSlice struct {
	MembershipID string                           `json:"membershipId"`
	Version      int64                            `json:"version"`
	GroupID      string                           `json:"groupId"`
	CircleID     string                           `json:"circleId"`
	PersonaID    string                           `json:"personaId"`
	Role         model.CircleGroupMembershipRole  `json:"role"`
	State        model.CircleGroupMembershipState `json:"state"`
	JoinedAt     *time.Time                       `json:"joinedAt"`
	LeftAt       *time.Time                       `json:"leftAt"`
	DecidedAt    *time.Time                       `json:"decidedAt"`
	CreatedAt    time.Time                        `json:"createdAt"`
	UpdatedAt    time.Time                        `json:"updatedAt"`
}

type MembershipPageResult struct {
	Items  []MembershipSlice `json:"items"`
	Cursor string            `json:"cursor,omitempty"`
}

type QueryFacade struct {
	groups      ports.GroupPolicyReader
	memberships ports.MembershipReader
}

func NewQueryFacade(groups ports.GroupPolicyReader, memberships ports.MembershipReader) *QueryFacade {
	if groups == nil || memberships == nil {
		panic("CircleGroupMembership QueryFacade requires named Readers")
	}
	return &QueryFacade{groups: groups, memberships: memberships}
}

func (facade *QueryFacade) GetMy(ctx context.Context, circleID, groupID string) (MembershipSlice, error) {
	actorID, err := trustedPersona(ctx)
	if err != nil {
		return MembershipSlice{}, err
	}
	if _, found, err := facade.groups.ReadGroupPolicy(ctx, strings.TrimSpace(circleID), strings.TrimSpace(groupID)); err != nil {
		return MembershipSlice{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	} else if !found {
		return MembershipSlice{}, grouperrors.AppErrorFromGroupNotFound("CircleGroup not found")
	}
	membership, found, err := facade.memberships.ReadGroupMembership(ctx, strings.TrimSpace(groupID), actorID)
	if err != nil {
		return MembershipSlice{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	if !found {
		return MembershipSlice{}, generated.AppErrorFromGroupMembershipNotFound("self group membership not found")
	}
	return newSlice(membership), nil
}

func (facade *QueryFacade) List(ctx context.Context, circleID, groupID, state string, limit int, cursor string) (MembershipPageResult, error) {
	actorID, err := trustedPersona(ctx)
	if err != nil {
		return MembershipPageResult{}, err
	}
	group, found, err := facade.groups.ReadGroupPolicy(ctx, strings.TrimSpace(circleID), strings.TrimSpace(groupID))
	if err != nil {
		return MembershipPageResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	if !found {
		return MembershipPageResult{}, grouperrors.AppErrorFromGroupNotFound("CircleGroup not found")
	}
	actorMembership, found, err := facade.memberships.ReadGroupMembership(ctx, group.GroupID, actorID)
	if err != nil {
		return MembershipPageResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	if !found || actorMembership.State != model.CircleGroupMembershipStateActive {
		return MembershipPageResult{}, circleerrors.AppErrorFromPermissionDenied("active group membership is required to list roster")
	}
	page, err := facade.memberships.ListGroupMemberships(ctx, group.GroupID, strings.TrimSpace(state), limit, cursor)
	if err != nil {
		return MembershipPageResult{}, generated.AppErrorFromGroupMembershipStorageWriteFailed(err.Error())
	}
	items := make([]MembershipSlice, 0, len(page.Items))
	for _, membership := range page.Items {
		items = append(items, newSlice(membership))
	}
	return MembershipPageResult{Items: items, Cursor: page.Cursor}, nil
}

func newSlice(membership model.CircleGroupMembership) MembershipSlice {
	return MembershipSlice{
		MembershipID: membership.ID, Version: membership.Version, GroupID: membership.GroupID,
		CircleID: membership.CircleID, PersonaID: membership.PersonaID, Role: membership.Role, State: membership.State,
		JoinedAt: timePointer(membership.JoinedAt), LeftAt: timePointer(membership.LeftAt),
		DecidedAt: timePointer(membership.DecidedAt), CreatedAt: membership.CreatedAt, UpdatedAt: membership.UpdatedAt,
	}
}

func timePointer(value time.Time) *time.Time {
	if value.IsZero() {
		return nil
	}
	return &value
}
