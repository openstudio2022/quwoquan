// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/spec.md#sit-001
// readiness_case: list-circle-groups-local
// readiness_case: search-circle-groups-local
// readiness_case: create-circle-group-local
// readiness_case: get-circle-group-local
// readiness_case: update-circle-group-local
// readiness_case: archive-circle-group-local
package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/operation"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/ports"
)

func TestCircleGroupFacadesExecuteEveryHTTPOperation(t *testing.T) {
	store := newGroupFacadeStore()
	commands := app.NewCommandFacade(store, store)
	queries := app.NewQueryFacade(store, store)
	ctx := groupOperationContext("persona-owner", "create-group")
	created, err := commands.Create(ctx, app.CreateCommand{
		CircleID: "circle-1", GroupType: model.CircleGroupTypeSelfBuilt,
		Name: "周末同行", Description: "同行协作",
		Visibility: model.CircleGroupVisibilityPublic,
		JoinPolicy: model.CircleGroupJoinPolicyApplyOnly,
	})
	if err != nil || created.Version != 1 || created.Status != string(model.CircleGroupStatusActive) {
		t.Fatalf("CreateCircleGroup drift: result=%+v err=%v", created, err)
	}
	detail, err := queries.Get(groupReadContext("persona-owner"), "circle-1", created.GroupID)
	if err != nil || detail.GroupID != created.GroupID {
		t.Fatalf("GetCircleGroup drift: detail=%+v err=%v", detail, err)
	}
	listed, err := queries.List(groupReadContext("persona-owner"), ports.ListQuery{
		CircleID: "circle-1", Limit: 20,
	})
	if err != nil || len(listed.Items) != 1 || listed.Items[0].GroupID != created.GroupID {
		t.Fatalf("ListCircleGroups drift: result=%+v err=%v", listed, err)
	}
	searched, err := queries.Search(groupReadContext("persona-owner"), ports.SearchRequestFact{
		CircleID: "circle-1", Query: "周末", Limit: 20,
	})
	if err != nil || len(searched.Items) != 1 || searched.Items[0].GroupID != created.GroupID {
		t.Fatalf("SearchCircleGroups drift: result=%+v err=%v", searched, err)
	}
	updatedName := "周末远足"
	updated, err := commands.Update(
		groupOperationContext("persona-owner", "update-group"),
		app.UpdateCommand{
			CircleID: "circle-1", GroupID: created.GroupID,
			ExpectedVersion: created.Version, Name: &updatedName,
		},
	)
	if err != nil || updated.Version != 2 || store.groups[created.GroupID].Name != updatedName {
		t.Fatalf("UpdateCircleGroup drift: result=%+v value=%+v err=%v", updated, store.groups[created.GroupID], err)
	}
	archived, err := commands.Archive(
		groupOperationContext("persona-owner", "archive-group"),
		app.ArchiveCommand{CircleID: "circle-1", GroupID: created.GroupID},
	)
	if err != nil || archived.Status != string(model.CircleGroupStatusArchived) {
		t.Fatalf("ArchiveCircleGroup drift: result=%+v err=%v", archived, err)
	}
}

type groupFacadeStore struct {
	groups map[string]model.CircleGroup
}

func newGroupFacadeStore() *groupFacadeStore {
	return &groupFacadeStore{groups: map[string]model.CircleGroup{}}
}

func (store *groupFacadeStore) Load(_ context.Context, groupID string) (model.CircleGroup, bool, error) {
	value, found := store.groups[groupID]
	return value, found, nil
}

func (store *groupFacadeStore) Commit(_ context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	var current *model.CircleGroup
	if value, found := store.groups[request.Change.GroupID]; found {
		copy := value
		current = &copy
	}
	next, err := model.Apply(current, request.Change)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	store.groups[next.ID] = next
	return ports.CommitReceipt{
		GroupID: next.ID, Version: next.Version, Status: next.Status,
	}, nil
}

func (store *groupFacadeStore) RecordNoopReceipt(_ context.Context, request ports.NoopReceipt) (ports.CommitReceipt, error) {
	return ports.CommitReceipt{
		GroupID: request.GroupID, Version: request.Version,
		Status: request.Status, Replayed: true,
	}, nil
}

func (store *groupFacadeStore) ReadCirclePolicy(_ context.Context, circleID string) (ports.CirclePolicySlice, bool, error) {
	return ports.CirclePolicySlice{CircleID: circleID, State: "active"}, true, nil
}

func (store *groupFacadeStore) ReadCircleMembership(_ context.Context, _ string, personaID string) (ports.CircleMembershipPolicySlice, bool, error) {
	return ports.CircleMembershipPolicySlice{PersonaID: personaID, Role: "owner", State: "active"}, true, nil
}

func (store *groupFacadeStore) ReadGroupMembership(_ context.Context, _ string, personaID string) (ports.GroupMembershipPolicySlice, bool, error) {
	return ports.GroupMembershipPolicySlice{PersonaID: personaID, Role: "owner", State: "active"}, true, nil
}

func (store *groupFacadeStore) ReadParent(context.Context, string, string) (model.CircleGroup, bool, error) {
	return model.CircleGroup{}, false, nil
}

func (store *groupFacadeStore) ParentChainContains(context.Context, string, string, string) (bool, error) {
	return false, nil
}

func (store *groupFacadeStore) ReadGroup(_ context.Context, circleID, groupID string) (ports.GroupReadSlice, bool, error) {
	value, found := store.groups[groupID]
	if !found || value.CircleID != circleID {
		return ports.GroupReadSlice{}, false, nil
	}
	return ports.GroupReadSlice{Group: value, MemberCount: 1}, true, nil
}

func (store *groupFacadeStore) ListGroups(_ context.Context, query ports.ListQuery) (ports.GroupPageSlice, error) {
	return store.page(query.CircleID), nil
}

func (store *groupFacadeStore) SearchGroups(_ context.Context, query ports.SearchRequestFact) (ports.GroupPageSlice, error) {
	return store.page(query.CircleID), nil
}

func (store *groupFacadeStore) page(circleID string) ports.GroupPageSlice {
	items := make([]ports.GroupReadSlice, 0, len(store.groups))
	for _, value := range store.groups {
		if value.CircleID == circleID {
			items = append(items, ports.GroupReadSlice{Group: value, MemberCount: 1})
		}
	}
	return ports.GroupPageSlice{Items: items}
}

func groupOperationContext(personaID, key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		IdempotencyKey: key, Actor: operation.ActorContext{PersonaID: personaID},
	})
}

func groupReadContext(personaID string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		Actor: operation.ActorContext{PersonaID: personaID},
	})
}
