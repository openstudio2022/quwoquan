package circlegroup

import (
	"errors"
	"testing"
	"time"
)

func TestCircleGroupAggregateOwnsPolicyButNotMembershipRoles(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	name, description := "旅行同好", "一起出发"
	visibility := CircleGroupVisibilityPrivate
	joinPolicy := CircleGroupJoinPolicyApplyOnly
	storage, notice := true, true
	created, err := Apply(nil, ChangeSet{
		Kind: ChangeCreate, GroupID: "group-1", CircleID: "circle-1",
		GroupType: CircleGroupTypeSelfBuilt, Name: &name, Description: &description,
		Visibility: &visibility, JoinPolicy: &joinPolicy, StorageEnabled: &storage,
		NoticeEnabled: &notice, CreatedByPersona: "persona-1", OccurredAt: now,
	})
	if err != nil {
		t.Fatalf("create CircleGroup: %v", err)
	}
	if created.Version != 1 || created.Status != CircleGroupStatusActive || created.IsDefaultPublicGroup {
		t.Fatalf("unexpected created aggregate: %#v", created)
	}

	updatedName := "远行同好"
	updated, err := Apply(&created, ChangeSet{
		Kind: ChangeUpdate, ExpectedVersion: 1, Name: &updatedName, OccurredAt: now.Add(time.Minute),
	})
	if err != nil || updated.Version != 2 || updated.Name != updatedName {
		t.Fatalf("update CircleGroup: %#v, %v", updated, err)
	}
	if _, err := Apply(&updated, ChangeSet{
		Kind: ChangeUpdate, ExpectedVersion: 1, Name: &updatedName, OccurredAt: now.Add(2 * time.Minute),
	}); !errors.Is(err, ErrVersionConflict) {
		t.Fatalf("expected version conflict, got %v", err)
	}
}

func TestCircleGroupRejectsInvalidHierarchyAndDefaultArchive(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	name := "默认公共群"
	visibility := CircleGroupVisibilityPublic
	joinPolicy := CircleGroupJoinPolicyApplyOnly
	enabled := true
	created, err := Apply(nil, ChangeSet{
		Kind: ChangeCreate, GroupID: "group-default", CircleID: "circle-1",
		GroupType: CircleGroupTypePublicGroup, Name: &name, Visibility: &visibility,
		JoinPolicy: &joinPolicy, StorageEnabled: &enabled, NoticeEnabled: &enabled,
		CreatedByPersona: "persona-owner", OccurredAt: now,
	})
	if err != nil || !created.IsDefaultPublicGroup {
		t.Fatalf("create default group: %#v, %v", created, err)
	}
	if _, err := Apply(&created, ChangeSet{
		Kind: ChangeArchive, ExpectedVersion: 1, OccurredAt: now.Add(time.Minute),
	}); !errors.Is(err, ErrDefaultCannotArchive) {
		t.Fatalf("expected default archive rejection, got %v", err)
	}
	self := created.ID
	if _, err := Apply(&created, ChangeSet{
		Kind: ChangeUpdate, ExpectedVersion: 1, ParentGroupID: &self, OccurredAt: now.Add(time.Minute),
	}); !errors.Is(err, ErrParentInvalid) {
		t.Fatalf("expected self-parent rejection, got %v", err)
	}
}

func TestOrganizationNodeRequiresTypedNodeKind(t *testing.T) {
	name := "组织节点"
	visibility := CircleGroupVisibilityPrivate
	joinPolicy := CircleGroupJoinPolicyInviteOnly
	enabled := true
	_, err := Apply(nil, ChangeSet{
		Kind: ChangeCreate, GroupID: "group-org", CircleID: "circle-1",
		GroupType: CircleGroupTypeOrgNode, Name: &name, Visibility: &visibility,
		JoinPolicy: &joinPolicy, StorageEnabled: &enabled, NoticeEnabled: &enabled,
		CreatedByPersona: "persona-owner", OccurredAt: time.Now().UTC(),
	})
	if !errors.Is(err, ErrInvalidChange) {
		t.Fatalf("expected missing node kind rejection, got %v", err)
	}
}
