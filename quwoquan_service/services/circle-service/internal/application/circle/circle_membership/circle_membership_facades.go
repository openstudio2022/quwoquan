package circlemembership

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	membershipmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/model"
	membershipports "quwoquan_service/services/circle-service/internal/domain/circle/circle_membership/ports"
	generated "quwoquan_service/services/circle-service/internal/generated"
)

const membershipReceiptRetention = 7 * 24 * time.Hour

type LeaveCommand struct {
	CircleID string
}

type UpdateRoleCommand struct {
	CircleID        string
	TargetPersonaID string
	Role            membershipmodel.CircleMemberRole
}

type CommandResult struct {
	MembershipID     string `json:"membershipId"`
	Version          int64  `json:"version"`
	State            string `json:"state"`
	Role             string `json:"role"`
	IdempotentReplay bool   `json:"idempotentReplay"`
}

type CommandFacade struct {
	store       membershipports.AggregateStore
	circles     membershipports.CirclePolicyReader
	memberships membershipports.MembershipReader
	now         func() time.Time
}

func NewCommandFacade(store membershipports.AggregateStore, circles membershipports.CirclePolicyReader, memberships membershipports.MembershipReader) *CommandFacade {
	if store == nil || circles == nil || memberships == nil {
		panic("CircleMembership CommandFacade requires Store and named Readers")
	}
	return &CommandFacade{store: store, circles: circles, memberships: memberships, now: time.Now}
}

func (facade *CommandFacade) Join(ctx context.Context, circleID string) (CommandResult, error) {
	currentContext, actorID, err := trustedMembershipContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	circle, err := facade.requireActiveCircle(ctx, circleID)
	if err != nil {
		return CommandResult{}, err
	}
	role := membershipmodel.CircleMemberRoleMember
	pending := false
	if actorID == circle.OwnerPersonaID {
		role = membershipmodel.CircleMemberRoleOwner
	} else if circle.JoinPolicy == "approval" {
		// 审批制圈子：加入意图建 pending 档，等待 owner/admin 审批（ApproveCircleMember）。
		pending = true
	} else if circle.JoinPolicy != "open" {
		return CommandResult{}, generated.AppErrorFromJoinApprovalRequired("Circle join policy does not allow direct membership creation")
	}
	membershipID := stableMembershipID(circle.CircleID, actorID)
	existing, found, loadErr := facade.store.LoadByIdentity(ctx, circle.CircleID, actorID)
	if loadErr != nil {
		return CommandResult{}, generated.AppErrorFromMembershipStorageWriteFailed(loadErr.Error())
	}
	expectedVersion := int64(0)
	if found {
		expectedVersion = existing.Version
	}
	return facade.commit(ctx, currentContext, actorID, membershipmodel.ChangeSet{
		Kind: membershipmodel.ChangeJoin, MembershipID: membershipID,
		CircleID: circle.CircleID, PersonaID: actorID, Role: role, Pending: pending,
		ExpectedVersion: expectedVersion, OccurredAt: facade.now().UTC(),
	})
}

// DecideCommand 是圈子级审批（Approve/Reject）的命令输入。
type DecideCommand struct {
	CircleID        string
	TargetPersonaID string
}

func (facade *CommandFacade) Approve(ctx context.Context, command DecideCommand) (CommandResult, error) {
	return facade.decide(ctx, command, membershipmodel.ChangeApprove)
}

func (facade *CommandFacade) Reject(ctx context.Context, command DecideCommand) (CommandResult, error) {
	return facade.decide(ctx, command, membershipmodel.ChangeReject)
}

func (facade *CommandFacade) decide(ctx context.Context, command DecideCommand, kind membershipmodel.ChangeKind) (CommandResult, error) {
	currentContext, actorID, err := trustedMembershipContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	circle, err := facade.requireActiveCircle(ctx, command.CircleID)
	if err != nil {
		return CommandResult{}, err
	}
	if err := facade.requireModerator(ctx, circle, actorID); err != nil {
		return CommandResult{}, err
	}
	targetPersonaID := strings.TrimSpace(command.TargetPersonaID)
	target, found, readErr := facade.store.LoadByIdentity(ctx, circle.CircleID, targetPersonaID)
	if readErr != nil {
		return CommandResult{}, generated.AppErrorFromMembershipStorageWriteFailed(readErr.Error())
	}
	if !found {
		return CommandResult{}, generated.AppErrorFromMembershipNotFound("target membership not found")
	}
	return facade.commit(ctx, currentContext, actorID, membershipmodel.ChangeSet{
		Kind: kind, MembershipID: target.ID,
		CircleID: target.CircleID, PersonaID: target.PersonaID,
		ExpectedVersion: target.Version, OccurredAt: facade.now().UTC(),
	})
}

func (facade *CommandFacade) requireModerator(ctx context.Context, circle membershipports.CirclePolicySlice, actorID string) error {
	if actorID == circle.OwnerPersonaID {
		return nil
	}
	actorMembership, found, readErr := facade.memberships.ReadCircleMembership(ctx, circle.CircleID, actorID)
	if readErr != nil {
		return generated.AppErrorFromMembershipStorageWriteFailed(readErr.Error())
	}
	if found && actorMembership.State == membershipmodel.CircleMembershipStateActive &&
		actorMembership.Role == membershipmodel.CircleMemberRoleAdmin {
		return nil
	}
	return generated.AppErrorFromPermissionDenied("Circle membership approval requires owner or admin")
}

func (facade *CommandFacade) Leave(ctx context.Context, command LeaveCommand) (CommandResult, error) {
	currentContext, actorID, err := trustedMembershipContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	membership, found, loadErr := facade.store.LoadByIdentity(ctx, strings.TrimSpace(command.CircleID), actorID)
	if loadErr != nil {
		return CommandResult{}, generated.AppErrorFromMembershipStorageWriteFailed(loadErr.Error())
	}
	if !found {
		return CommandResult{}, generated.AppErrorFromMembershipNotFound("self membership not found")
	}
	return facade.commit(ctx, currentContext, actorID, membershipmodel.ChangeSet{
		Kind: membershipmodel.ChangeLeave, MembershipID: membership.ID,
		CircleID: membership.CircleID, PersonaID: actorID,
		ExpectedVersion: membership.Version, OccurredAt: facade.now().UTC(),
	})
}

func (facade *CommandFacade) UpdateRole(ctx context.Context, command UpdateRoleCommand) (CommandResult, error) {
	currentContext, actorID, err := trustedMembershipContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	circle, err := facade.requireActiveCircle(ctx, command.CircleID)
	if err != nil {
		return CommandResult{}, err
	}
	if err := facade.requireModerator(ctx, circle, actorID); err != nil {
		return CommandResult{}, err
	}
	targetPersonaID := strings.TrimSpace(command.TargetPersonaID)
	target, found, readErr := facade.store.LoadByIdentity(ctx, circle.CircleID, targetPersonaID)
	if readErr != nil {
		return CommandResult{}, generated.AppErrorFromMembershipStorageWriteFailed(readErr.Error())
	}
	if !found {
		return CommandResult{}, generated.AppErrorFromMembershipNotFound("target membership not found")
	}
	return facade.commit(ctx, currentContext, actorID, membershipmodel.ChangeSet{
		Kind: membershipmodel.ChangeRole, MembershipID: target.ID,
		CircleID: target.CircleID, PersonaID: target.PersonaID, Role: command.Role,
		ExpectedVersion: target.Version, OccurredAt: facade.now().UTC(),
	})
}

func (facade *CommandFacade) requireActiveCircle(ctx context.Context, circleID string) (membershipports.CirclePolicySlice, error) {
	circle, found, err := facade.circles.ReadCirclePolicy(ctx, strings.TrimSpace(circleID))
	if err != nil {
		return membershipports.CirclePolicySlice{}, generated.AppErrorFromMembershipStorageWriteFailed(err.Error())
	}
	if !found {
		return membershipports.CirclePolicySlice{}, generated.AppErrorFromCircleNotFound("CircleMembership target Circle not found")
	}
	if circle.State != "active" {
		return membershipports.CirclePolicySlice{}, generated.AppErrorFromInvalidArgument("CircleMembership target Circle is not active")
	}
	return circle, nil
}

func (facade *CommandFacade) commit(ctx context.Context, current operation.Context, actorID string, change membershipmodel.ChangeSet) (CommandResult, error) {
	digest, err := membershipCommandDigest(actorID, change)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromMembershipStorageWriteFailed(err.Error())
	}
	for attempt := 0; attempt < 3; attempt++ {
		receipt, commitErr := facade.store.Commit(ctx, membershipports.CommitRequest{
			Change: change, ReceiptKey: membershipReceiptKey(actorID, current.IdempotencyKey),
			CommandDigest: digest, ReceiptExpiresAt: facade.now().UTC().Add(membershipReceiptRetention),
		})
		if commitErr == nil {
			return CommandResult{
				MembershipID: receipt.MembershipID, Version: receipt.Version,
				State: string(receipt.State), Role: string(receipt.Role), IdempotentReplay: receipt.Replayed,
			}, nil
		}
		if !errors.Is(commitErr, membershipmodel.ErrVersionConflict) || attempt == 2 {
			return CommandResult{}, mapMembershipCommitError(commitErr)
		}
		latest, found, loadErr := facade.store.LoadByIdentity(
			ctx,
			change.CircleID,
			change.PersonaID,
		)
		if loadErr != nil {
			return CommandResult{}, generated.AppErrorFromMembershipStorageWriteFailed(loadErr.Error())
		}
		if !found {
			return CommandResult{}, mapMembershipCommitError(membershipmodel.ErrNotFound)
		}
		change.ExpectedVersion = latest.Version
	}
	panic("unreachable CircleMembership commit retry")
}

func trustedMembershipContext(ctx context.Context) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil || strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", generated.AppErrorFromInvalidArgument("trusted persona and Idempotency-Key are required")
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func membershipCommandDigest(actorID string, change membershipmodel.ChangeSet) (string, error) {
	payload, err := json.Marshal(struct {
		ActorID      string                           `json:"actorId"`
		Kind         membershipmodel.ChangeKind       `json:"kind"`
		MembershipID string                           `json:"membershipId"`
		CircleID     string                           `json:"circleId"`
		PersonaID    string                           `json:"personaId"`
		Role         membershipmodel.CircleMemberRole `json:"role"`
		Pending      bool                             `json:"pending"`
	}{actorID, change.Kind, change.MembershipID, change.CircleID, change.PersonaID, change.Role, change.Pending})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func membershipReceiptKey(actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return hex.EncodeToString(sum[:])
}

func stableMembershipID(circleID, personaID string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(circleID) + "\x00" + strings.TrimSpace(personaID)))
	return "cm_" + hex.EncodeToString(sum[:16])
}

func mapMembershipCommitError(err error) error {
	switch {
	case errors.Is(err, membershipmodel.ErrAlreadyActive):
		return generated.AppErrorFromMembershipAlreadyActive(err.Error())
	case errors.Is(err, membershipmodel.ErrNotFound):
		return generated.AppErrorFromMembershipNotFound(err.Error())
	case errors.Is(err, membershipmodel.ErrOwnerCannotLeave):
		return generated.AppErrorFromMembershipOwnerCannotLeave(err.Error())
	case errors.Is(err, membershipmodel.ErrInvalidRole):
		return generated.AppErrorFromMembershipRoleInvalid(err.Error())
	case errors.Is(err, membershipmodel.ErrVersionConflict):
		return generated.AppErrorFromMembershipVersionConflict(err.Error())
	case errors.Is(err, membershipmodel.ErrIdempotencyConflict):
		return generated.AppErrorFromMembershipIdempotencyConflict(err.Error())
	case errors.Is(err, membershipmodel.ErrStateConflict):
		return generated.AppErrorFromMembershipStateConflict(err.Error())
	case errors.Is(err, membershipmodel.ErrInvalidChange):
		return generated.AppErrorFromInvalidArgument(err.Error())
	default:
		return generated.AppErrorFromMembershipStorageWriteFailed(err.Error())
	}
}

type MembershipPageResult struct {
	Items  []MembershipSlice `json:"items"`
	Cursor string            `json:"cursor,omitempty"`
}

// MembershipSlice is the named Reader result. It deliberately does not reuse
// the aggregate persistence model so storage identity (_id) cannot leak into
// the public bounded-context contract.
type MembershipSlice struct {
	MembershipID string                                `json:"membershipId"`
	Version      int64                                 `json:"version"`
	CircleID     string                                `json:"circleId"`
	PersonaID    string                                `json:"personaId"`
	Role         membershipmodel.CircleMemberRole      `json:"role"`
	State        membershipmodel.CircleMembershipState `json:"state"`
	JoinedAt     time.Time                             `json:"joinedAt"`
	LeftAt       *time.Time                            `json:"leftAt"`
	LastActiveAt *time.Time                            `json:"lastActiveAt"`
	Contribution int64                                 `json:"contribution"`
	CreatedAt    time.Time                             `json:"createdAt"`
	UpdatedAt    time.Time                             `json:"updatedAt"`
}

type PersonaCirclePageResult struct {
	Items  []membershipports.CircleSummary `json:"items"`
	Cursor string                          `json:"cursor,omitempty"`
}

type QueryFacade struct {
	memberships    membershipports.MembershipReader
	personaCircles membershipports.PersonaCircleReader
	policies       membershipports.CirclePolicyReader
}

func NewQueryFacade(memberships membershipports.MembershipReader, personaCircles membershipports.PersonaCircleReader, policies membershipports.CirclePolicyReader) *QueryFacade {
	if memberships == nil || personaCircles == nil || policies == nil {
		panic("CircleMembership QueryFacade requires named Readers")
	}
	return &QueryFacade{
		memberships: memberships, personaCircles: personaCircles, policies: policies,
	}
}

func (facade *QueryFacade) ListCircleMemberships(ctx context.Context, circleID string, limit int, cursor string) (MembershipPageResult, error) {
	slice, err := facade.memberships.ListCircleMemberships(ctx, strings.TrimSpace(circleID), limit, cursor)
	if err != nil {
		return MembershipPageResult{}, generated.AppErrorFromMembershipStorageWriteFailed(err.Error())
	}
	items := make([]MembershipSlice, 0, len(slice.Items))
	for _, membership := range slice.Items {
		items = append(items, newMembershipSlice(membership))
	}
	return MembershipPageResult{Items: items, Cursor: slice.Cursor}, nil
}

// ListPendingCircleMemberships 返回待审批队列；仅圈主或 active admin 可读。
func (facade *QueryFacade) ListPendingCircleMemberships(ctx context.Context, circleID string, limit int, cursor string) (MembershipPageResult, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return MembershipPageResult{}, generated.AppErrorFromInvalidArgument("trusted persona is required")
	}
	actorID := strings.TrimSpace(current.Actor.PersonaID)
	trimmedCircleID := strings.TrimSpace(circleID)
	circle, found, err := facade.policies.ReadCirclePolicy(ctx, trimmedCircleID)
	if err != nil {
		return MembershipPageResult{}, generated.AppErrorFromMembershipStorageWriteFailed(err.Error())
	}
	if !found {
		return MembershipPageResult{}, generated.AppErrorFromCircleNotFound("CircleMembership target Circle not found")
	}
	moderator := actorID == circle.OwnerPersonaID
	if !moderator {
		actorMembership, memberFound, readErr := facade.memberships.ReadCircleMembership(ctx, trimmedCircleID, actorID)
		if readErr != nil {
			return MembershipPageResult{}, generated.AppErrorFromMembershipStorageWriteFailed(readErr.Error())
		}
		moderator = memberFound && actorMembership.State == membershipmodel.CircleMembershipStateActive &&
			actorMembership.Role == membershipmodel.CircleMemberRoleAdmin
	}
	if !moderator {
		return MembershipPageResult{}, generated.AppErrorFromPermissionDenied("Circle pending membership queue requires owner or admin")
	}
	slice, err := facade.memberships.ListPendingCircleMemberships(ctx, trimmedCircleID, limit, cursor)
	if err != nil {
		return MembershipPageResult{}, generated.AppErrorFromMembershipStorageWriteFailed(err.Error())
	}
	items := make([]MembershipSlice, 0, len(slice.Items))
	for _, membership := range slice.Items {
		items = append(items, newMembershipSlice(membership))
	}
	return MembershipPageResult{Items: items, Cursor: slice.Cursor}, nil
}

func (facade *QueryFacade) GetMyCircleMembership(ctx context.Context, circleID string) (MembershipSlice, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return MembershipSlice{}, generated.AppErrorFromInvalidArgument("trusted persona is required")
	}
	membership, found, err := facade.memberships.ReadCircleMembership(
		ctx, strings.TrimSpace(circleID), strings.TrimSpace(current.Actor.PersonaID),
	)
	if err != nil {
		return MembershipSlice{}, generated.AppErrorFromMembershipStorageWriteFailed(err.Error())
	}
	if !found {
		return MembershipSlice{}, generated.AppErrorFromMembershipNotFound("self membership not found")
	}
	return newMembershipSlice(membership), nil
}

func newMembershipSlice(membership membershipmodel.CircleMembership) MembershipSlice {
	var leftAt *time.Time
	if !membership.LeftAt.IsZero() {
		value := membership.LeftAt
		leftAt = &value
	}
	var lastActiveAt *time.Time
	if !membership.LastActiveAt.IsZero() {
		value := membership.LastActiveAt
		lastActiveAt = &value
	}
	return MembershipSlice{
		MembershipID: membership.ID,
		Version:      membership.Version,
		CircleID:     membership.CircleID,
		PersonaID:    membership.PersonaID,
		Role:         membership.Role,
		State:        membership.State,
		JoinedAt:     membership.JoinedAt,
		LeftAt:       leftAt,
		LastActiveAt: lastActiveAt,
		Contribution: membership.Contribution,
		CreatedAt:    membership.CreatedAt,
		UpdatedAt:    membership.UpdatedAt,
	}
}

func (facade *QueryFacade) ListPersonaCircles(
	ctx context.Context,
	personaID string,
	query string,
	limit int,
	cursor string,
) (PersonaCirclePageResult, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return PersonaCirclePageResult{}, generated.AppErrorFromInvalidArgument(
			"personaId is required",
		)
	}
	viewerPersonaID := ""
	if current, ok := operation.FromContext(ctx); ok {
		viewerPersonaID = strings.TrimSpace(current.Actor.PersonaID)
	}
	slice, err := facade.personaCircles.ListPersonaCircles(
		ctx,
		membershipports.PersonaCircleQuery{
			PersonaID:       personaID,
			ViewerPersonaID: viewerPersonaID,
			Query:           strings.TrimSpace(query),
			Limit:           limit,
			Cursor:          strings.TrimSpace(cursor),
		},
	)
	if err != nil {
		return PersonaCirclePageResult{}, generated.AppErrorFromMembershipStorageWriteFailed(err.Error())
	}
	return PersonaCirclePageResult{Items: slice.Items, Cursor: slice.Cursor}, nil
}
