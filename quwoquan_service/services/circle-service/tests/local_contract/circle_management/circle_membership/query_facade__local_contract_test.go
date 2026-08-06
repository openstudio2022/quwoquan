// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/spec.md#sit-002
// readiness_case: list-persona-circles-local
package local_contract

import (
	"context"
	. "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/application"
	"testing"

	"quwoquan_service/runtime/operation"
	membershipmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
	membershipports "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/ports"
)

type recordingQueryFacadeReader struct {
	personaCircleQuery  membershipports.PersonaCircleQuery
	personaCircleResult membershipports.PersonaCircleSlice
}

func (reader *recordingQueryFacadeReader) ReadCircleMembership(
	context.Context,
	string,
	string,
) (membershipmodel.CircleMembership, bool, error) {
	return membershipmodel.CircleMembership{}, false, nil
}

func (reader *recordingQueryFacadeReader) ListCircleMemberships(
	context.Context,
	string,
	int,
	string,
) (membershipports.MembershipSlice, error) {
	return membershipports.MembershipSlice{}, nil
}

func (reader *recordingQueryFacadeReader) ListPendingCircleMemberships(
	context.Context,
	string,
	int,
	string,
) (membershipports.MembershipSlice, error) {
	return membershipports.MembershipSlice{}, nil
}

func (reader *recordingQueryFacadeReader) ReadCirclePolicy(
	context.Context,
	string,
) (membershipports.CirclePolicySlice, bool, error) {
	return membershipports.CirclePolicySlice{}, false, nil
}

func (reader *recordingQueryFacadeReader) ListPersonaCircles(
	_ context.Context,
	query membershipports.PersonaCircleQuery,
) (membershipports.PersonaCircleSlice, error) {
	reader.personaCircleQuery = query
	return reader.personaCircleResult, nil
}

func TestListPersonaCirclesCarriesViewerSearchAndCursorToNamedReader(
	t *testing.T,
) {
	reader := &recordingQueryFacadeReader{
		personaCircleResult: membershipports.PersonaCircleSlice{
			Items: []membershipports.CircleSummary{{
				ID: "circle-public", Name: "公开摄影圈", Visibility: "public",
			}},
			Cursor: "membership-next",
		},
	}
	facade := NewQueryFacade(reader, reader, reader)
	ctx := operation.WithContext(context.Background(), operation.Context{
		Actor: operation.ActorContext{PersonaID: "persona-subject"},
	})

	result, err := facade.ListPersonaCircles(
		ctx,
		" persona-subject ",
		" 摄影 ",
		12,
		" membership-cursor ",
	)
	if err != nil {
		t.Fatalf("ListPersonaCircles returned error: %v", err)
	}
	if len(result.Items) != 1 || result.Items[0].ID != "circle-public" {
		t.Fatalf("unexpected result: %#v", result)
	}
	if result.Cursor != "membership-next" {
		t.Fatalf("cursor=%q want membership-next", result.Cursor)
	}
	want := membershipports.PersonaCircleQuery{
		PersonaID:       "persona-subject",
		ViewerPersonaID: "persona-subject",
		Query:           "摄影",
		Limit:           12,
		Cursor:          "membership-cursor",
	}
	if reader.personaCircleQuery != want {
		t.Fatalf("reader query=%#v want %#v", reader.personaCircleQuery, want)
	}
}

func TestListPersonaCirclesTreatsAnonymousRequestAsPublicViewer(t *testing.T) {
	reader := &recordingQueryFacadeReader{}
	facade := NewQueryFacade(reader, reader, reader)

	if _, err := facade.ListPersonaCircles(
		context.Background(),
		"persona-subject",
		"",
		20,
		"",
	); err != nil {
		t.Fatalf("ListPersonaCircles returned error: %v", err)
	}
	if reader.personaCircleQuery.ViewerPersonaID != "" {
		t.Fatalf(
			"anonymous viewer leaked as %q",
			reader.personaCircleQuery.ViewerPersonaID,
		)
	}
}
