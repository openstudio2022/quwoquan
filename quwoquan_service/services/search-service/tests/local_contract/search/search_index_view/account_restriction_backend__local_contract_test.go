// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package local_contract

import (
	"context"
	"errors"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

type restrictionReaderStub struct {
	restricted map[string]bool
	err        error
}

func (stub restrictionReaderStub) RestrictedSubjects(
	context.Context,
	[]string,
) (map[string]bool, error) {
	return stub.restricted, stub.err
}

func TestAccountRestrictionBackendFiltersBeforeRanking(t *testing.T) {
	inner := rtsearch.NewSliceBackend([]rtsearch.Document{
		{
			ObjectType: rtsearch.ObjectTypeContentPost,
			ObjectID:   "post-suspended",
			Fields:     map[string]string{"authorId": "persona-suspended"},
		},
		{
			ObjectType: rtsearch.ObjectTypeContentPost,
			ObjectID:   "post-active",
			Fields:     map[string]string{"authorId": "persona-active"},
		},
		{
			ObjectType: rtsearch.ObjectTypeUserProfile,
			ObjectID:   "user-suspended",
		},
	})
	backend, err := application.NewAccountRestrictionBackend(
		inner,
		restrictionReaderStub{restricted: map[string]bool{
			"persona-suspended": true,
			"user-suspended":    true,
		}},
	)
	if err != nil {
		t.Fatal(err)
	}
	candidates, err := backend.Recall(t.Context(), rtsearch.RetrievePlan{})
	if err != nil {
		t.Fatal(err)
	}
	if len(candidates) != 1 || candidates[0].Document.ObjectID != "post-active" {
		t.Fatalf("unexpected visible candidates: %+v", candidates)
	}
}

func TestAccountRestrictionBackendFailsClosed(t *testing.T) {
	inner := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType: rtsearch.ObjectTypeContentPost,
		ObjectID:   "post-private",
		Fields:     map[string]string{"authorId": "persona-private"},
	}})
	backend, err := application.NewAccountRestrictionBackend(
		inner,
		restrictionReaderStub{err: errors.New("restriction state unavailable")},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := backend.Recall(t.Context(), rtsearch.RetrievePlan{}); err == nil {
		t.Fatal("restriction reader failure must fail search recall closed")
	}
}
