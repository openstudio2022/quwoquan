package circlegroup

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	generated "quwoquan_service/services/circle-service/generated/circle_management/circle"
	groupmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
	groupports "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/ports"
)

const groupReceiptRetention = 7 * 24 * time.Hour

type CreateCommand struct {
	CircleID       string
	ParentGroupID  *string
	GroupType      groupmodel.CircleGroupType
	NodeType       *groupmodel.OrganizationNodeType
	Name           string
	Description    string
	Visibility     groupmodel.CircleGroupVisibility
	JoinPolicy     groupmodel.CircleGroupJoinPolicy
	StorageEnabled bool
	NoticeEnabled  bool
}

type UpdateCommand struct {
	CircleID        string
	GroupID         string
	ExpectedVersion int64
	ParentGroupID   *string
	NodeType        *groupmodel.OrganizationNodeType
	Name            *string
	Description     *string
	Visibility      *groupmodel.CircleGroupVisibility
	JoinPolicy      *groupmodel.CircleGroupJoinPolicy
	StorageEnabled  *bool
	NoticeEnabled   *bool
}

type ArchiveCommand struct {
	CircleID string
	GroupID  string
}

type CommandResult struct {
	GroupID          string `json:"groupId"`
	Version          int64  `json:"version"`
	Status           string `json:"status"`
	IdempotentReplay bool   `json:"idempotentReplay"`
}

type CommandFacade struct {
	store    groupports.AggregateStore
	policies groupports.PolicyReader
	now      func() time.Time
}

func NewCommandFacade(store groupports.AggregateStore, policies groupports.PolicyReader) *CommandFacade {
	if store == nil || policies == nil {
		panic("CircleGroup CommandFacade requires Store and named policy Readers")
	}
	return &CommandFacade{store: store, policies: policies, now: time.Now}
}

func (facade *CommandFacade) Create(ctx context.Context, command CreateCommand) (CommandResult, error) {
	current, actorID, err := trustedGroupCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	circleID := strings.TrimSpace(command.CircleID)
	membership, err := facade.requireActiveCircleMember(ctx, circleID, actorID)
	if err != nil {
		return CommandResult{}, err
	}
	if command.GroupType != groupmodel.CircleGroupTypeSelfBuilt && membership.Role != "owner" && membership.Role != "admin" {
		return CommandResult{}, generated.AppErrorFromPermissionDenied("public groups and organization nodes require Circle owner or admin")
	}
	groupID := stableGroupID(circleID, actorID, current.IdempotencyKey)
	if err := facade.validateParent(ctx, circleID, groupID, command.ParentGroupID); err != nil {
		return CommandResult{}, err
	}
	name, description := command.Name, command.Description
	visibility, joinPolicy := command.Visibility, command.JoinPolicy
	storageEnabled, noticeEnabled := command.StorageEnabled, command.NoticeEnabled
	return facade.commit(ctx, current, actorID, groupmodel.ChangeSet{
		Kind: groupmodel.ChangeCreate, GroupID: groupID, CircleID: circleID,
		ParentGroupID: command.ParentGroupID, GroupType: command.GroupType, NodeType: command.NodeType,
		Name: &name, Description: &description, Visibility: &visibility, JoinPolicy: &joinPolicy,
		StorageEnabled: &storageEnabled, NoticeEnabled: &noticeEnabled,
		CreatedByPersona: actorID, OccurredAt: facade.now().UTC(),
	})
}

func (facade *CommandFacade) Update(ctx context.Context, command UpdateCommand) (CommandResult, error) {
	current, actorID, err := trustedGroupCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	group, err := facade.requireGroupModerator(ctx, command.CircleID, command.GroupID, actorID, false)
	if err != nil {
		return CommandResult{}, err
	}
	if command.ExpectedVersion <= 0 {
		return CommandResult{}, generated.AppErrorFromInvalidArgument("If-Match version is required")
	}
	if err := facade.validateParent(ctx, group.CircleID, group.ID, command.ParentGroupID); err != nil {
		return CommandResult{}, err
	}
	return facade.commit(ctx, current, actorID, groupmodel.ChangeSet{
		Kind: groupmodel.ChangeUpdate, GroupID: group.ID, CircleID: group.CircleID,
		ExpectedVersion: command.ExpectedVersion, ParentGroupID: command.ParentGroupID,
		NodeType: command.NodeType, Name: command.Name, Description: command.Description,
		Visibility: command.Visibility, JoinPolicy: command.JoinPolicy,
		StorageEnabled: command.StorageEnabled, NoticeEnabled: command.NoticeEnabled,
		OccurredAt: facade.now().UTC(),
	})
}

func (facade *CommandFacade) Archive(ctx context.Context, command ArchiveCommand) (CommandResult, error) {
	current, actorID, err := trustedGroupCommandContext(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	group, err := facade.requireGroupModerator(ctx, command.CircleID, command.GroupID, actorID, true)
	if err != nil {
		return CommandResult{}, err
	}
	change := groupmodel.ChangeSet{
		Kind: groupmodel.ChangeArchive, GroupID: group.ID, CircleID: group.CircleID,
		ExpectedVersion: group.Version, OccurredAt: facade.now().UTC(),
	}
	if group.Status == groupmodel.CircleGroupStatusArchived {
		return facade.recordNoop(ctx, current, actorID, group, change)
	}
	return facade.commit(ctx, current, actorID, change)
}

// recordNoop 持久化"目标状态已满足"回执；首个 Idempotency-Key 也能重放原始结果。
func (facade *CommandFacade) recordNoop(ctx context.Context, current operation.Context, actorID string, group groupmodel.CircleGroup, change groupmodel.ChangeSet) (CommandResult, error) {
	digest, err := groupCommandDigest(actorID, change)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	receipt, err := facade.store.RecordNoopReceipt(ctx, groupports.NoopReceipt{
		GroupID: group.ID, Version: group.Version, Status: group.Status,
		ReceiptKey:    groupReceiptKey(actorID, current.IdempotencyKey),
		CommandDigest: digest, ReceiptExpiresAt: facade.now().UTC().Add(groupReceiptRetention),
	})
	if err != nil {
		return CommandResult{}, mapGroupCommitError(err)
	}
	return CommandResult{
		GroupID: receipt.GroupID, Version: receipt.Version,
		Status: string(receipt.Status), IdempotentReplay: true,
	}, nil
}

func (facade *CommandFacade) requireActiveCircleMember(ctx context.Context, circleID, personaID string) (groupports.CircleMembershipPolicySlice, error) {
	circle, found, err := facade.policies.ReadCirclePolicy(ctx, circleID)
	if err != nil {
		return groupports.CircleMembershipPolicySlice{}, generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	if !found || circle.State != "active" {
		return groupports.CircleMembershipPolicySlice{}, generated.AppErrorFromCircleNotFound("CircleGroup target Circle is not active")
	}
	membership, found, err := facade.policies.ReadCircleMembership(ctx, circleID, personaID)
	if err != nil {
		return groupports.CircleMembershipPolicySlice{}, generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	if !found || membership.State != "active" {
		return groupports.CircleMembershipPolicySlice{}, generated.AppErrorFromNotMember("active CircleMembership is required")
	}
	return membership, nil
}

func (facade *CommandFacade) requireGroupModerator(ctx context.Context, circleID, groupID, personaID string, ownerOnly bool) (groupmodel.CircleGroup, error) {
	group, found, err := facade.store.Load(ctx, strings.TrimSpace(groupID))
	if err != nil {
		return groupmodel.CircleGroup{}, generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	if !found || group.CircleID != strings.TrimSpace(circleID) {
		return groupmodel.CircleGroup{}, generated.AppErrorFromGroupNotFound("CircleGroup not found in Circle")
	}
	membership, found, err := facade.policies.ReadGroupMembership(ctx, group.ID, personaID)
	if err != nil {
		return groupmodel.CircleGroup{}, generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	allowed := found && membership.State == "active" && membership.Role == "owner"
	if !ownerOnly {
		allowed = allowed || (found && membership.State == "active" && membership.Role == "manager")
	}
	if !allowed {
		return groupmodel.CircleGroup{}, generated.AppErrorFromPermissionDenied("CircleGroup owner or manager role is required")
	}
	return group, nil
}

func (facade *CommandFacade) validateParent(ctx context.Context, circleID, groupID string, parentID *string) error {
	if parentID == nil || strings.TrimSpace(*parentID) == "" {
		return nil
	}
	parent, found, err := facade.policies.ReadParent(ctx, circleID, strings.TrimSpace(*parentID))
	if err != nil {
		return generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	if !found || parent.Status != groupmodel.CircleGroupStatusActive || parent.CircleID != circleID || parent.ID == groupID {
		return generated.AppErrorFromGroupParentInvalid("parent must be an active CircleGroup in the same Circle")
	}
	contains, err := facade.policies.ParentChainContains(ctx, circleID, parent.ID, groupID)
	if err != nil {
		return generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	if contains {
		return generated.AppErrorFromGroupParentInvalid("parent chain would form a cycle")
	}
	return nil
}

func (facade *CommandFacade) commit(ctx context.Context, current operation.Context, actorID string, change groupmodel.ChangeSet) (CommandResult, error) {
	digest, err := groupCommandDigest(actorID, change)
	if err != nil {
		return CommandResult{}, generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	for attempt := 0; attempt < 3; attempt++ {
		receipt, commitErr := facade.store.Commit(ctx, groupports.CommitRequest{
			Change: change, ReceiptKey: groupReceiptKey(actorID, current.IdempotencyKey),
			CommandDigest: digest, ReceiptExpiresAt: facade.now().UTC().Add(groupReceiptRetention),
		})
		if commitErr == nil {
			return CommandResult{GroupID: receipt.GroupID, Version: receipt.Version, Status: string(receipt.Status), IdempotentReplay: receipt.Replayed}, nil
		}
		if change.Kind != groupmodel.ChangeArchive ||
			!errors.Is(commitErr, groupmodel.ErrVersionConflict) ||
			attempt == 2 {
			return CommandResult{}, mapGroupCommitError(commitErr)
		}
		latest, found, loadErr := facade.store.Load(ctx, change.GroupID)
		if loadErr != nil {
			return CommandResult{}, generated.AppErrorFromGroupStorageWriteFailed(loadErr.Error())
		}
		if !found {
			return CommandResult{}, mapGroupCommitError(groupmodel.ErrNotFound)
		}
		if latest.Status == groupmodel.CircleGroupStatusArchived {
			return facade.recordNoop(ctx, current, actorID, latest, change)
		}
		change.ExpectedVersion = latest.Version
	}
	panic("unreachable CircleGroup commit retry")
}

func trustedGroupCommandContext(ctx context.Context) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil || strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", generated.AppErrorFromInvalidArgument("trusted persona and Idempotency-Key are required")
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func groupCommandDigest(actorID string, change groupmodel.ChangeSet) (string, error) {
	copy := change
	copy.OccurredAt = time.Time{}
	if copy.Kind == groupmodel.ChangeArchive {
		copy.ExpectedVersion = 0
	}
	payload, err := json.Marshal(struct {
		ActorID string               `json:"actorId"`
		Change  groupmodel.ChangeSet `json:"change"`
	}{ActorID: actorID, Change: copy})
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func groupReceiptKey(actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return hex.EncodeToString(sum[:])
}

func stableGroupID(circleID, actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(circleID) + "\x00" + strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return "cg_" + hex.EncodeToString(sum[:16])
}

func mapGroupCommitError(err error) error {
	switch {
	case errors.Is(err, groupmodel.ErrNotFound):
		return generated.AppErrorFromGroupNotFound(err.Error())
	case errors.Is(err, groupmodel.ErrArchived):
		return generated.AppErrorFromGroupArchived(err.Error())
	case errors.Is(err, groupmodel.ErrParentInvalid):
		return generated.AppErrorFromGroupParentInvalid(err.Error())
	case errors.Is(err, groupmodel.ErrDefaultConflict):
		return generated.AppErrorFromGroupDefaultConflict(err.Error())
	case errors.Is(err, groupmodel.ErrDefaultCannotArchive):
		return generated.AppErrorFromGroupDefaultCannotArchive(err.Error())
	case errors.Is(err, groupmodel.ErrVersionConflict):
		return generated.AppErrorFromGroupVersionConflict(err.Error())
	case errors.Is(err, groupmodel.ErrIdempotencyConflict):
		return generated.AppErrorFromGroupIdempotencyConflict(err.Error())
	case errors.Is(err, groupmodel.ErrInvalidChange):
		return generated.AppErrorFromInvalidArgument(err.Error())
	default:
		return generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
}

type GroupSlice struct {
	GroupID              string                           `json:"groupId"`
	Version              int64                            `json:"version"`
	CircleID             string                           `json:"circleId"`
	ParentGroupID        string                           `json:"parentGroupId,omitempty"`
	GroupType            groupmodel.CircleGroupType       `json:"groupType"`
	NodeType             groupmodel.OrganizationNodeType  `json:"nodeType,omitempty"`
	Name                 string                           `json:"name"`
	Description          string                           `json:"description,omitempty"`
	Visibility           groupmodel.CircleGroupVisibility `json:"visibility"`
	JoinPolicy           groupmodel.CircleGroupJoinPolicy `json:"joinPolicy"`
	ConversationID       string                           `json:"conversationId,omitempty"`
	StorageEnabled       bool                             `json:"storageEnabled"`
	NoticeEnabled        bool                             `json:"noticeEnabled"`
	IsDefaultPublicGroup bool                             `json:"isDefaultPublicGroup"`
	Status               groupmodel.CircleGroupStatus     `json:"status"`
	MemberCount          int64                            `json:"memberCount"`
	CreatedAt            time.Time                        `json:"createdAt"`
	UpdatedAt            time.Time                        `json:"updatedAt"`
}

type PageResult struct {
	Items  []GroupSlice `json:"items"`
	Cursor string       `json:"cursor,omitempty"`
}

type QueryFacade struct {
	readers  groupports.GroupReader
	policies groupports.PolicyReader
}

func NewQueryFacade(readers groupports.GroupReader, policies groupports.PolicyReader) *QueryFacade {
	if readers == nil || policies == nil {
		panic("CircleGroup QueryFacade requires named Readers")
	}
	return &QueryFacade{readers: readers, policies: policies}
}

func (facade *QueryFacade) Get(ctx context.Context, circleID, groupID string) (GroupSlice, error) {
	if _, _, err := facade.requireReaderActor(ctx, circleID); err != nil {
		return GroupSlice{}, err
	}
	value, found, err := facade.readers.ReadGroup(ctx, strings.TrimSpace(circleID), strings.TrimSpace(groupID))
	if err != nil {
		return GroupSlice{}, generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	if !found {
		return GroupSlice{}, generated.AppErrorFromGroupNotFound("CircleGroup not found")
	}
	return newGroupSlice(value), nil
}

func (facade *QueryFacade) List(ctx context.Context, query groupports.ListQuery) (PageResult, error) {
	if _, _, err := facade.requireReaderActor(ctx, query.CircleID); err != nil {
		return PageResult{}, err
	}
	page, err := facade.readers.ListGroups(ctx, query)
	if err != nil {
		return PageResult{}, generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	return newPageResult(page), nil
}

func (facade *QueryFacade) Search(ctx context.Context, query groupports.SearchQuery) (PageResult, error) {
	if _, _, err := facade.requireReaderActor(ctx, query.CircleID); err != nil {
		return PageResult{}, err
	}
	if strings.TrimSpace(query.Query) == "" {
		return PageResult{}, generated.AppErrorFromInvalidArgument("CircleGroup search query is required")
	}
	page, err := facade.readers.SearchGroups(ctx, query)
	if err != nil {
		return PageResult{}, generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	return newPageResult(page), nil
}

func (facade *QueryFacade) requireReaderActor(ctx context.Context, circleID string) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorPersona) != nil {
		return operation.Context{}, "", generated.AppErrorFromInvalidArgument("trusted persona is required")
	}
	actorID := strings.TrimSpace(current.Actor.PersonaID)
	membership, found, err := facade.policies.ReadCircleMembership(ctx, strings.TrimSpace(circleID), actorID)
	if err != nil {
		return operation.Context{}, "", generated.AppErrorFromGroupStorageWriteFailed(err.Error())
	}
	if !found || membership.State != "active" {
		return operation.Context{}, "", generated.AppErrorFromNotMember("active CircleMembership is required")
	}
	return current, actorID, nil
}

func newPageResult(page groupports.GroupPageSlice) PageResult {
	items := make([]GroupSlice, 0, len(page.Items))
	for _, item := range page.Items {
		items = append(items, newGroupSlice(item))
	}
	return PageResult{Items: items, Cursor: page.Cursor}
}

func newGroupSlice(value groupports.GroupReadSlice) GroupSlice {
	group := value.Group
	return GroupSlice{
		GroupID: group.ID, Version: group.Version, CircleID: group.CircleID,
		ParentGroupID: group.ParentGroupID, GroupType: group.GroupType, NodeType: group.NodeType,
		Name: group.Name, Description: group.Description, Visibility: group.Visibility,
		JoinPolicy: group.JoinPolicy, ConversationID: group.ConversationID,
		StorageEnabled: group.StorageEnabled, NoticeEnabled: group.NoticeEnabled,
		IsDefaultPublicGroup: group.IsDefaultPublicGroup, Status: group.Status,
		MemberCount: value.MemberCount, CreatedAt: group.CreatedAt.UTC(), UpdatedAt: group.UpdatedAt.UTC(),
	}
}
