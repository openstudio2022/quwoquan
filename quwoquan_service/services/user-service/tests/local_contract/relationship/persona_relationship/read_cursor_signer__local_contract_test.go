package local_contract

import (
	"errors"
	"strings"
	"testing"
	"time"

	relapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
)

func TestRelationshipReadCursorBindsWholeQuery(t *testing.T) {
	signer, err := relapp.NewReadCursorSigner([]byte(strings.Repeat("c", 32)))
	if err != nil {
		t.Fatal(err)
	}
	claims := relapp.ReadCursorClaims{
		OwnerPersonaID: "owner", ViewerPersonaID: "viewer", Direction: "following",
		Query: "  Travel   CAT ", PositionAt: time.Unix(123, 456).UTC(), PositionPairID: "pair-1",
	}
	token, err := signer.Issue(claims)
	if err != nil {
		t.Fatal(err)
	}
	verified, err := signer.Verify(token, relapp.ReadCursorClaims{
		OwnerPersonaID: "owner", ViewerPersonaID: "viewer", Direction: "following", Query: "travel cat",
	})
	if err != nil || verified.PositionPairID != "pair-1" {
		t.Fatalf("verified=%+v err=%v", verified, err)
	}
	for name, mutate := range map[string]func(*relapp.ReadCursorClaims){
		"owner":     func(value *relapp.ReadCursorClaims) { value.OwnerPersonaID = "other" },
		"viewer":    func(value *relapp.ReadCursorClaims) { value.ViewerPersonaID = "other" },
		"direction": func(value *relapp.ReadCursorClaims) { value.Direction = "followers" },
		"query":     func(value *relapp.ReadCursorClaims) { value.Query = "dog" },
	} {
		t.Run(name, func(t *testing.T) {
			expected := claims
			mutate(&expected)
			if _, err := signer.Verify(token, expected); !errors.Is(err, relapp.ErrInvalidReadCursor) {
				t.Fatalf("cross-query cursor err=%v", err)
			}
		})
	}
	tampered := token[:len(token)-1] + "A"
	if _, err := signer.Verify(tampered, claims); !errors.Is(err, relapp.ErrInvalidReadCursor) {
		t.Fatalf("tampered cursor err=%v", err)
	}
}
