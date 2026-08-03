// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-placement-collaboration/spec.md#gwt-001
package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/travel-service/internal/travel/trip_membership/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/infrastructure/sourcereference"
)

type delegatedSourceAuthorization struct {
	personaID string
}

func (authorization *delegatedSourceAuthorization) AuthorizationHeaderForPersona(
	_ context.Context,
	personaID string,
) (string, error) {
	authorization.personaID = personaID
	return "Bearer delegated-" + personaID, nil
}

func TestTripMembershipSourceReadersVerifyTargetPersonaAndExactSourceVersion(t *testing.T) {
	authorization := &delegatedSourceAuthorization{}
	chat := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.EscapedPath() != "/chat/conversations/conversation-1" ||
			request.Header.Get("Authorization") != "Bearer delegated-member" {
			t.Fatalf("Chat request=%s auth=%q", request.URL.String(), request.Header.Get("Authorization"))
		}
		_, _ = writer.Write([]byte(`{"id":"conversation-1","membersRosterRevision":8,"status":"active"}`))
	}))
	t.Cleanup(chat.Close)
	circle := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Header.Get("Authorization") != "Bearer delegated-member" {
			t.Fatalf("Circle request auth=%q", request.Header.Get("Authorization"))
		}
		switch request.URL.EscapedPath() {
		case "/circles/circle-1/memberships/self":
			_, _ = writer.Write([]byte(`{"version":4,"circleId":"circle-1","personaId":"member","state":"active"}`))
		case "/gatherings/gathering-1":
			_, _ = writer.Write([]byte(`{"gatheringId":"gathering-1","version":6,"participants":[{"personaId":"member","state":"joined"}]}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(circle.Close)

	conversation, err := sourcereference.NewConversationResolver(chat.URL, chat.Client(), authorization)
	if err != nil {
		t.Fatal(err)
	}
	circleMembership, err := sourcereference.NewCircleMembershipResolver(circle.URL, circle.Client(), authorization)
	if err != nil {
		t.Fatal(err)
	}
	gathering, err := sourcereference.NewGatheringResolver(circle.URL, circle.Client(), authorization)
	if err != nil {
		t.Fatal(err)
	}
	authority := application.NewSourceAuthority(map[model.SourceKind]application.MembershipSourceResolver{
		model.SourceConversation: conversation,
		model.SourceCircle:       circleMembership,
		model.SourceGathering:    gathering,
	})
	tests := []struct {
		kind    model.SourceKind
		ref     model.SourceRef
		version int64
	}{
		{model.SourceConversation, model.SourceRef{ObjectTypeRef: "chat.Conversation", ObjectID: "conversation-1"}, 8},
		{model.SourceCircle, model.SourceRef{ObjectTypeRef: "circle.Circle", ObjectID: "circle-1"}, 4},
		{model.SourceGathering, model.SourceRef{ObjectTypeRef: "circle.Gathering", ObjectID: "gathering-1"}, 6},
	}
	for _, test := range tests {
		ref := test.ref
		if err := authority.ValidateMembershipSource(
			t.Context(), test.kind, &ref, test.version, "member",
		); err != nil {
			t.Fatalf("%s source error=%v", test.kind, err)
		}
	}
	if authorization.personaID != "member" {
		t.Fatalf("delegated persona=%q", authorization.personaID)
	}
}

func TestTripMembershipSourceReaderRejectsStaleSourceVersion(t *testing.T) {
	authorization := &delegatedSourceAuthorization{}
	chat := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = writer.Write([]byte(`{"id":"conversation-1","membersRosterRevision":8,"status":"active"}`))
	}))
	t.Cleanup(chat.Close)
	resolver, err := sourcereference.NewConversationResolver(chat.URL, chat.Client(), authorization)
	if err != nil {
		t.Fatal(err)
	}
	err = resolver.ValidateMembershipSource(
		t.Context(),
		model.SourceRef{ObjectTypeRef: "chat.Conversation", ObjectID: "conversation-1"},
		7,
		"member",
	)
	if err == nil {
		t.Fatal("stale Conversation roster revision was accepted")
	}
}
