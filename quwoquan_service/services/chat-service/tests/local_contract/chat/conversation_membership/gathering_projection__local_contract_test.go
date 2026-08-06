// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
// readiness_case: project-gathering-conversation-membership-local
package local_contract

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	membershiphttp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/adapters/inbound/http"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

func TestGatheringProjectionRejectsClientForgedRoleAndAccess(t *testing.T) {
	backend := newGatheringProjectionBackend()
	facade := membershipapp.NewGatheringProjectionFacade(
		backend, backend, backend, backend, backend, backend, backend, backend,
	)
	routes := http.NewServeMux()
	membershiphttp.NewGatheringProjectionHandler(facade).Register(routes)
	request := httptest.NewRequest(
		http.MethodPut,
		"/internal/chat/gathering-conversations/gathering-1/members/persona-2",
		strings.NewReader(`{"sourceEventId":"forged","sourceVersion":1,"sourceType":"organizer_assignment","state":"active"}`),
	)
	response := httptest.NewRecorder()
	routes.ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized || backend.members["persona-2"] != nil {
		t.Fatalf("untrusted projection status=%d body=%s backend=%+v", response.Code, response.Body.String(), backend)
	}
}

func TestGatheringProjectionConvergesMembershipAndRejectsVersionReuse(t *testing.T) {
	backend := newGatheringProjectionBackend()
	facade := membershipapp.NewGatheringProjectionFacade(
		backend, backend, backend, backend, backend, backend, backend, backend,
	)
	command := membershipapp.GatheringProjectionCommand{
		SourceEventID: "gathering-1:participation:persona-2:20", SourceVersion: 20,
		GatheringID: "gathering-1", PersonaID: "persona-2",
		SourceType: membershipapp.GatheringProjectionSourceParticipation,
		State:      membershipapp.GatheringProjectionStateActive,
	}
	result, err := facade.Project(context.Background(), command)
	if err != nil {
		t.Fatalf("Project joined: %v", err)
	}
	if result.ConversationID != "conversation-1" || backend.members["persona-2"] == nil ||
		result.AccessRole != membershipapp.GatheringAccessRoleParticipant ||
		backend.members["persona-2"].Role != "member" ||
		!backend.userStates["persona-2"] || backend.memberCount != 2 {
		t.Fatalf("joined projection did not converge: result=%+v backend=%+v", result, backend)
	}
	if len(backend.membershipEvents) != 1 || len(backend.conversationEvents) != 1 {
		t.Fatalf("projection outbox counts = membership:%d conversation:%d", len(backend.membershipEvents), len(backend.conversationEvents))
	}

	if _, err := facade.Project(context.Background(), command); err != nil {
		t.Fatalf("exact replay must be idempotent: %v", err)
	}
	if len(backend.membershipEvents) != 1 || backend.memberCount != 2 {
		t.Fatal("exact replay emitted a second side effect")
	}

	conflict := command
	conflict.SourceEventID = "gathering-1:another-fact"
	if _, err := facade.Project(context.Background(), conflict); err == nil {
		t.Fatal("same sourceVersion with another event must fail closed")
	}

	organizer := command
	organizer.SourceEventID = "gathering-1:organizer:persona-2:10"
	organizer.SourceVersion = 10
	organizer.SourceType = membershipapp.GatheringProjectionSourceOrganizerAssignment
	if result, err := facade.Project(context.Background(), organizer); err != nil {
		t.Fatalf("Project organizer: %v", err)
	} else if result.AccessRole != membershipapp.GatheringAccessRoleAdmin ||
		backend.members["persona-2"].Role != "admin" {
		t.Fatalf("organizer must derive admin access: result=%+v member=%+v", result, backend.members["persona-2"])
	}

	closed := command
	closed.SourceEventID = "gathering-1:participation:persona-2:30"
	closed.SourceVersion = 30
	closed.State = membershipapp.GatheringProjectionStateClosed
	if result, err := facade.Project(context.Background(), closed); err != nil {
		t.Fatalf("Project closed Participation: %v", err)
	} else if result.AccessRole != membershipapp.GatheringAccessRoleAdmin ||
		backend.members["persona-2"].Role != "admin" {
		t.Fatalf("active OrganizerAssignment must retain admin access: %+v", result)
	}

	blocked := command
	blocked.SourceEventID = "gathering-1:block:persona-2:40"
	blocked.SourceVersion = 40
	blocked.SourceType = membershipapp.GatheringProjectionSourceBlock
	blocked.State = membershipapp.GatheringProjectionStateBlocked
	if result, err := facade.Project(context.Background(), blocked); err != nil {
		t.Fatalf("Project Block: %v", err)
	} else if result.AccessStatus != membershipapp.GatheringAccessStatusRevoked {
		t.Fatalf("Block must revoke access: %+v", result)
	}
	if backend.members["persona-2"] != nil || backend.userStates["persona-2"] || backend.memberCount != 1 {
		t.Fatalf("Block did not revoke Chat access: %+v", backend)
	}

	if _, err := facade.Project(context.Background(), organizer); err != nil {
		t.Fatalf("old OrganizerAssignment replay must be no-op: %v", err)
	}
	if backend.members["persona-2"] != nil {
		t.Fatal("old grant must not override newer Block")
	}

	cleared := blocked
	cleared.SourceEventID = "gathering-1:block:persona-2:50"
	cleared.SourceVersion = 50
	cleared.State = membershipapp.GatheringProjectionStateCleared
	if result, err := facade.Project(context.Background(), cleared); err != nil {
		t.Fatalf("clear Block: %v", err)
	} else if result.AccessRole != membershipapp.GatheringAccessRoleAdmin ||
		backend.members["persona-2"] == nil || backend.members["persona-2"].Role != "admin" {
		t.Fatalf("clearing Block must restore current organizer grant: result=%+v backend=%+v", result, backend)
	}
}

type gatheringProjectionBackend struct {
	members            map[string]*membershipmodel.Member
	userStates         map[string]bool
	states             map[string]membershipapp.GatheringProjectionState
	membershipEvents   []membershipapp.GatheringOutboxEvent
	conversationEvents []membershipapp.GatheringOutboxEvent
	memberCount        int
}

func newGatheringProjectionBackend() *gatheringProjectionBackend {
	return &gatheringProjectionBackend{
		members: map[string]*membershipmodel.Member{
			"persona-owner": {
				ID: "member-owner", ConversationId: "conversation-1", UserId: "persona-owner",
				MemberType: "user", Role: "owner", JoinedAt: time.Now().UTC(),
			},
		},
		userStates: map[string]bool{"persona-owner": true},
		states:     map[string]membershipapp.GatheringProjectionState{}, memberCount: 1,
	}
}

func (backend *gatheringProjectionBackend) RunInTransaction(ctx context.Context, apply func(context.Context) error) error {
	return apply(ctx)
}

func (backend *gatheringProjectionBackend) ReadGatheringConversation(context.Context, string) (membershipapp.GatheringBinding, bool, error) {
	return membershipapp.GatheringBinding{
		GatheringID: "gathering-1", ConversationID: "conversation-1",
		Active: true,
	}, true, nil
}

func (backend *gatheringProjectionBackend) CreateMember(_ context.Context, member *membershipmodel.Member) error {
	if backend.members[member.UserId] != nil {
		return fmt.Errorf("duplicate member")
	}
	copy := *member
	backend.members[member.UserId] = &copy
	return nil
}

func (backend *gatheringProjectionBackend) DeleteMember(_ context.Context, _, userID string) error {
	delete(backend.members, userID)
	return nil
}

func (backend *gatheringProjectionBackend) FindMember(_ context.Context, _, userID string) (*membershipmodel.Member, error) {
	member := backend.members[userID]
	if member == nil {
		return nil, fmt.Errorf("%w: %s", membershipmodel.ErrNotFound, userID)
	}
	copy := *member
	return &copy, nil
}

func (backend *gatheringProjectionBackend) UpdateMemberRole(_ context.Context, _, userID, role string) error {
	member := backend.members[userID]
	if member == nil {
		return fmt.Errorf("%w: %s", membershipmodel.ErrNotFound, userID)
	}
	member.Role = role
	return nil
}

func (backend *gatheringProjectionBackend) CountUserMembers(context.Context, string) (int, error) {
	return len(backend.members), nil
}

func (backend *gatheringProjectionBackend) EnsureGatheringUserState(_ context.Context, userID, _ string, _ time.Time) error {
	backend.userStates[userID] = true
	return nil
}

func (backend *gatheringProjectionBackend) DeleteGatheringUserState(_ context.Context, userID, _ string) error {
	delete(backend.userStates, userID)
	return nil
}

func (backend *gatheringProjectionBackend) BumpGatheringRoster(_ context.Context, _ string, memberCount int) error {
	backend.memberCount = memberCount
	return nil
}

func (backend *gatheringProjectionBackend) ReadGatheringMemberProfile(context.Context, string) (membershipapp.GatheringMemberProfile, error) {
	return membershipapp.GatheringMemberProfile{DisplayName: "同行者"}, nil
}

func (backend *gatheringProjectionBackend) LoadGatheringProjectionState(_ context.Context, gatheringID, personaID, sourceType string) (membershipapp.GatheringProjectionState, bool, error) {
	state, found := backend.states[gatheringID+":"+personaID+":"+sourceType]
	return state, found, nil
}

func (backend *gatheringProjectionBackend) SaveGatheringProjectionState(_ context.Context, state membershipapp.GatheringProjectionState) error {
	backend.states[state.GatheringID+":"+state.PersonaID+":"+state.SourceType] = state
	return nil
}

func (backend *gatheringProjectionBackend) AppendGatheringProjectionEvents(_ context.Context, membershipEvents, conversationEvents []membershipapp.GatheringOutboxEvent) error {
	backend.membershipEvents = append(backend.membershipEvents, membershipEvents...)
	backend.conversationEvents = append(backend.conversationEvents, conversationEvents...)
	return nil
}
