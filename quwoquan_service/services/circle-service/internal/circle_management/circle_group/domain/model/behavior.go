package circlegroup

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrNotFound             = errors.New("CircleGroup not found")
	ErrArchived             = errors.New("CircleGroup is archived")
	ErrInvalidChange        = errors.New("invalid CircleGroup change")
	ErrParentInvalid        = errors.New("CircleGroup parent is invalid")
	ErrDefaultConflict      = errors.New("default public CircleGroup already exists")
	ErrDefaultCannotArchive = errors.New("default public CircleGroup cannot be archived")
	ErrVersionConflict      = errors.New("CircleGroup version conflict")
	ErrIdempotencyConflict  = errors.New("CircleGroup idempotency conflict")
)

type ChangeKind string

const (
	ChangeCreate  ChangeKind = "create"
	ChangeUpdate  ChangeKind = "update"
	ChangeArchive ChangeKind = "archive"
)

// ChangeSet is the only mutation input accepted by the CircleGroup aggregate.
// Path identity and actor metadata are resolved by the application Facade.
type ChangeSet struct {
	Kind             ChangeKind
	GroupID          string
	CircleID         string
	ExpectedVersion  int64
	ParentGroupID    *string
	GroupType        CircleGroupType
	NodeType         *OrganizationNodeType
	Name             *string
	Description      *string
	Visibility       *CircleGroupVisibility
	JoinPolicy       *CircleGroupJoinPolicy
	StorageEnabled   *bool
	NoticeEnabled    *bool
	CreatedByPersona string
	OccurredAt       time.Time
}

func Apply(current *CircleGroup, change ChangeSet) (CircleGroup, error) {
	switch change.Kind {
	case ChangeCreate:
		if current != nil || change.ExpectedVersion != 0 {
			return CircleGroup{}, ErrVersionConflict
		}
		return createGroup(change)
	case ChangeUpdate:
		if current == nil {
			return CircleGroup{}, ErrNotFound
		}
		if current.Version != change.ExpectedVersion {
			return CircleGroup{}, ErrVersionConflict
		}
		if current.Status != CircleGroupStatusActive {
			return CircleGroup{}, ErrArchived
		}
		return updateGroup(*current, change)
	case ChangeArchive:
		if current == nil {
			return CircleGroup{}, ErrNotFound
		}
		if current.Version != change.ExpectedVersion {
			return CircleGroup{}, ErrVersionConflict
		}
		if current.IsDefaultPublicGroup {
			return CircleGroup{}, ErrDefaultCannotArchive
		}
		if current.Status == CircleGroupStatusArchived {
			return CircleGroup{}, ErrArchived
		}
		next := *current
		next.Version++
		next.Status = CircleGroupStatusArchived
		next.UpdatedAt = change.OccurredAt.UTC()
		return next, nil
	default:
		return CircleGroup{}, ErrInvalidChange
	}
}

func createGroup(change ChangeSet) (CircleGroup, error) {
	groupID := strings.TrimSpace(change.GroupID)
	circleID := strings.TrimSpace(change.CircleID)
	creator := strings.TrimSpace(change.CreatedByPersona)
	if groupID == "" || circleID == "" || creator == "" || change.OccurredAt.IsZero() ||
		change.Name == nil || change.Visibility == nil || change.JoinPolicy == nil ||
		change.StorageEnabled == nil || change.NoticeEnabled == nil {
		return CircleGroup{}, ErrInvalidChange
	}
	if !validGroupType(change.GroupType) || !validVisibility(*change.Visibility) || !validJoinPolicy(*change.JoinPolicy) {
		return CircleGroup{}, ErrInvalidChange
	}
	name := strings.TrimSpace(*change.Name)
	if name == "" || len([]rune(name)) > 80 {
		return CircleGroup{}, ErrInvalidChange
	}
	description := ""
	if change.Description != nil {
		description = strings.TrimSpace(*change.Description)
	}
	if len([]rune(description)) > 2000 {
		return CircleGroup{}, ErrInvalidChange
	}
	parentID := ""
	if change.ParentGroupID != nil {
		parentID = strings.TrimSpace(*change.ParentGroupID)
	}
	if parentID == groupID {
		return CircleGroup{}, ErrParentInvalid
	}
	nodeType := OrganizationNodeType("")
	if change.NodeType != nil {
		nodeType = *change.NodeType
	}
	if !validNodeType(change.GroupType, nodeType) {
		return CircleGroup{}, ErrInvalidChange
	}
	now := change.OccurredAt.UTC()
	return CircleGroup{
		ID: groupID, Version: 1, CircleID: circleID, ParentGroupID: parentID,
		GroupType: change.GroupType, NodeType: nodeType, Name: name, Description: description,
		Visibility: *change.Visibility, JoinPolicy: *change.JoinPolicy,
		CreatedByPersonaID: creator, StorageEnabled: *change.StorageEnabled,
		NoticeEnabled:        *change.NoticeEnabled,
		IsDefaultPublicGroup: change.GroupType == CircleGroupTypePublicGroup,
		Status:               CircleGroupStatusActive, CreatedAt: now, UpdatedAt: now,
	}, nil
}

func updateGroup(next CircleGroup, change ChangeSet) (CircleGroup, error) {
	changed := false
	if change.ParentGroupID != nil {
		parentID := strings.TrimSpace(*change.ParentGroupID)
		if parentID == next.ID {
			return CircleGroup{}, ErrParentInvalid
		}
		next.ParentGroupID, changed = parentID, true
	}
	if change.NodeType != nil {
		next.NodeType, changed = *change.NodeType, true
	}
	if change.Name != nil {
		name := strings.TrimSpace(*change.Name)
		if name == "" || len([]rune(name)) > 80 {
			return CircleGroup{}, ErrInvalidChange
		}
		next.Name, changed = name, true
	}
	if change.Description != nil {
		description := strings.TrimSpace(*change.Description)
		if len([]rune(description)) > 2000 {
			return CircleGroup{}, ErrInvalidChange
		}
		next.Description, changed = description, true
	}
	if change.Visibility != nil {
		if !validVisibility(*change.Visibility) {
			return CircleGroup{}, ErrInvalidChange
		}
		next.Visibility, changed = *change.Visibility, true
	}
	if change.JoinPolicy != nil {
		if !validJoinPolicy(*change.JoinPolicy) {
			return CircleGroup{}, ErrInvalidChange
		}
		next.JoinPolicy, changed = *change.JoinPolicy, true
	}
	if change.StorageEnabled != nil {
		next.StorageEnabled, changed = *change.StorageEnabled, true
	}
	if change.NoticeEnabled != nil {
		next.NoticeEnabled, changed = *change.NoticeEnabled, true
	}
	if !changed || !validNodeType(next.GroupType, next.NodeType) {
		return CircleGroup{}, ErrInvalidChange
	}
	next.Version++
	next.UpdatedAt = change.OccurredAt.UTC()
	return next, nil
}

func validGroupType(value CircleGroupType) bool {
	return value == CircleGroupTypePublicGroup || value == CircleGroupTypeSelfBuilt || value == CircleGroupTypeOrgNode
}

func validVisibility(value CircleGroupVisibility) bool {
	return value == CircleGroupVisibilityPublic || value == CircleGroupVisibilityPrivate
}

func validJoinPolicy(value CircleGroupJoinPolicy) bool {
	return value == CircleGroupJoinPolicyApplyOnly || value == CircleGroupJoinPolicyInviteOnly
}

func validNodeType(groupType CircleGroupType, value OrganizationNodeType) bool {
	if groupType != CircleGroupTypeOrgNode {
		return value == ""
	}
	switch value {
	case OrganizationNodeTypeGeneric, OrganizationNodeTypeCollege, OrganizationNodeTypeGrade,
		OrganizationNodeTypeClassroom, OrganizationNodeTypeDepartment, OrganizationNodeTypeTeam:
		return true
	default:
		return false
	}
}
