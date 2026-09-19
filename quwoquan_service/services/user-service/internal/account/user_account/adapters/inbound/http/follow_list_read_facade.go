package http

import (
	"context"
	"errors"

	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

type followListRelationshipReader interface {
	ListFollowing(context.Context, string, string, int, string, string) ([]relmodel.Direction, string, error)
	ListFollowers(context.Context, string, string, int, string, string) ([]relmodel.Direction, string, error)
	GetRelationships(context.Context, string, []string) (map[string]relmodel.RelationshipState, error)
}

type followListPersonaReader interface {
	GetFollowListProfileViews(context.Context, []string) (map[string]accountapp.FollowListProfileView, error)
}

type followListGreetingReader interface {
	HasPendingBetweenMany(context.Context, string, []string) (map[string]bool, error)
	HasFormalConversationMany(context.Context, string, []string) (map[string]bool, error)
}

type followListReadFacade struct {
	relationship followListRelationshipReader
	personas     followListPersonaReader
	greetings    followListGreetingReader
}

type followListPageFacts struct {
	Edges               []relmodel.Direction
	NextCursor          string
	Profiles            map[string]accountapp.FollowListProfileView
	Relationships       map[string]relmodel.RelationshipState
	PendingGreetings    map[string]bool
	FormalConversations map[string]bool
}

func (f followListReadFacade) Read(
	ctx context.Context,
	viewerID, ownerID, cursor string,
	limit int,
	following bool,
	query string,
) (followListPageFacts, error) {
	if f.relationship == nil || f.personas == nil || (viewerID != "" && f.greetings == nil) {
		return followListPageFacts{}, errors.New("follow list safety dependency unavailable")
	}
	var facts followListPageFacts
	var err error
	if following {
		facts.Edges, facts.NextCursor, err = f.relationship.ListFollowing(ctx, ownerID, cursor, limit, viewerID, query)
	} else {
		facts.Edges, facts.NextCursor, err = f.relationship.ListFollowers(ctx, ownerID, cursor, limit, viewerID, query)
	}
	if err != nil {
		return followListPageFacts{}, err
	}
	targetIDs := followListTargetIDs(facts.Edges, following)
	facts.Profiles, err = f.personas.GetFollowListProfileViews(ctx, targetIDs)
	if err != nil {
		return followListPageFacts{}, err
	}
	facts.Relationships = map[string]relmodel.RelationshipState{}
	facts.PendingGreetings = map[string]bool{}
	facts.FormalConversations = map[string]bool{}
	if viewerID == "" || len(targetIDs) == 0 {
		return facts, nil
	}
	facts.Relationships, err = f.relationship.GetRelationships(ctx, viewerID, targetIDs)
	if err != nil {
		return followListPageFacts{}, err
	}
	facts.PendingGreetings, err = f.greetings.HasPendingBetweenMany(ctx, viewerID, targetIDs)
	if err != nil {
		return followListPageFacts{}, err
	}
	facts.FormalConversations, err = f.greetings.HasFormalConversationMany(ctx, viewerID, targetIDs)
	if err != nil {
		return followListPageFacts{}, err
	}
	return facts, nil
}

func followListTargetIDs(edges []relmodel.Direction, following bool) []string {
	result := make([]string, 0, len(edges))
	for _, edge := range edges {
		targetID := edge.SourcePersonaID
		if following {
			targetID = edge.TargetPersonaID
		}
		if targetID != "" {
			result = append(result, targetID)
		}
	}
	return result
}

var _ followListRelationshipReader = (relationshipapp.Facade)(nil)
