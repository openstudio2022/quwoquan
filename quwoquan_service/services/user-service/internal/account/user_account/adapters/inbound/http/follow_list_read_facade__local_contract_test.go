package http

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

type countingFollowRelationship struct{ listCalls, batchCalls int }

func (r *countingFollowRelationship) ListFollowing(_ context.Context, owner, _ string, limit int, _, _ string) ([]relmodel.Direction, string, error) {
	r.listCalls++
	items := make([]relmodel.Direction, limit)
	now := time.Now().UTC()
	for i := range items {
		items[i] = relmodel.Direction{PairID: fmt.Sprintf("pair-%03d", i), SourcePersonaID: owner, TargetPersonaID: fmt.Sprintf("target-%03d", i), Following: true, FollowedAt: &now}
	}
	return items, "next", nil
}
func (r *countingFollowRelationship) ListFollowers(context.Context, string, string, int, string, string) ([]relmodel.Direction, string, error) {
	return nil, "", errors.New("unexpected followers call")
}
func (r *countingFollowRelationship) GetRelationships(_ context.Context, _ string, targets []string) (map[string]relmodel.RelationshipState, error) {
	r.batchCalls++
	result := make(map[string]relmodel.RelationshipState, len(targets))
	return result, nil
}

type countingFollowProfiles struct{ calls int }

func (p *countingFollowProfiles) GetFollowListProfileViews(_ context.Context, targets []string) (map[string]accountapp.FollowListProfileView, error) {
	p.calls++
	result := make(map[string]accountapp.FollowListProfileView, len(targets))
	for _, target := range targets {
		result[target] = accountapp.FollowListProfileView{PersonaID: target}
	}
	return result, nil
}

type countingFollowGreetings struct {
	pendingCalls, formalCalls int
	fail                      error
}

func (g *countingFollowGreetings) HasPendingBetweenMany(context.Context, string, []string) (map[string]bool, error) {
	g.pendingCalls++
	if g.fail != nil {
		return nil, g.fail
	}
	return map[string]bool{}, nil
}
func (g *countingFollowGreetings) HasFormalConversationMany(context.Context, string, []string) (map[string]bool, error) {
	g.formalCalls++
	return map[string]bool{}, nil
}

func TestFollowListReadFacadeHasFixedDependencyTrips(t *testing.T) {
	for _, size := range []int{20, 100} {
		relationships := &countingFollowRelationship{}
		profiles := &countingFollowProfiles{}
		greetings := &countingFollowGreetings{}
		facts, err := (followListReadFacade{relationships, profiles, greetings}).Read(t.Context(), "viewer", "owner", "", size, true, "")
		if err != nil || len(facts.Edges) != size {
			t.Fatalf("size=%d facts=%d err=%v", size, len(facts.Edges), err)
		}
		if relationships.listCalls != 1 || relationships.batchCalls != 1 || profiles.calls != 1 || greetings.pendingCalls != 1 || greetings.formalCalls != 1 {
			t.Fatalf("size=%d trips list=%d relations=%d profiles=%d pending=%d formal=%d", size, relationships.listCalls, relationships.batchCalls, profiles.calls, greetings.pendingCalls, greetings.formalCalls)
		}
	}
}

func TestFollowListReadFacadeFailsClosedOnSafetyDependency(t *testing.T) {
	dependencyErr := errors.New("greeting store unavailable")
	_, err := (followListReadFacade{&countingFollowRelationship{}, &countingFollowProfiles{}, &countingFollowGreetings{fail: dependencyErr}}).Read(t.Context(), "viewer", "owner", "", 20, true, "")
	if !errors.Is(err, dependencyErr) {
		t.Fatalf("err=%v", err)
	}
	_, err = (followListReadFacade{relationship: &countingFollowRelationship{}, personas: &countingFollowProfiles{}}).Read(t.Context(), "viewer", "owner", "", 20, true, "")
	if err == nil {
		t.Fatal("missing greeting safety dependency must not become an empty page")
	}
}
