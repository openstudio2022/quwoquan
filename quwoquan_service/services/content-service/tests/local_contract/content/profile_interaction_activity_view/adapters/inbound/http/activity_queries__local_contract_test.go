// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-009
// readiness_case: list-profile-interaction-activities-received-local
// readiness_case: list-profile-interaction-activities-sent-local
package http_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	activityhttp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/adapters/inbound/http"
	activityapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	activitymodel "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/model"
	activityports "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/ports"
)

func TestActivityHTTPQueriesUseTheProductionFacadeAndPreserveDirection(t *testing.T) {
	t.Parallel()

	reader := &recordingActivityReader{}
	handler := activityhttp.NewHandler(activityapp.NewActivityQueryService(reader))

	for _, scenario := range []struct {
		name      string
		personaID string
		direction string
		invoke    func(http.ResponseWriter, *http.Request)
	}{
		{
			name: "received", personaID: "profile-owner",
			direction: activitymodel.DirectionReceived, invoke: handler.ListReceived,
		},
		{
			name: "sent", personaID: "profile-actor",
			direction: activitymodel.DirectionSent, invoke: handler.ListSent,
		},
	} {
		t.Run(scenario.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodGet,
				"/content/personas/"+scenario.personaID+"/interactions/"+scenario.name+"?type=like&limit=20",
				nil,
			)
			request.SetPathValue("personaId", scenario.personaID)
			request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
				Actor: operation.ActorContext{PersonaID: scenario.personaID},
			}))
			recorder := httptest.NewRecorder()
			scenario.invoke(recorder, request)
			if recorder.Code != http.StatusOK ||
				!strings.Contains(recorder.Body.String(), `"direction":"`+scenario.direction+`"`) ||
				!strings.Contains(recorder.Body.String(), `"activityId":"activity-`+scenario.direction+`"`) {
				t.Fatalf("%s status=%d body=%s", scenario.name, recorder.Code, recorder.Body.String())
			}
		})
	}

	if len(reader.requests) != 2 ||
		reader.requests[0].Direction != activitymodel.DirectionReceived ||
		reader.requests[1].Direction != activitymodel.DirectionSent ||
		reader.requests[0].OwnerPersonaID != "profile-owner" ||
		reader.requests[1].OwnerPersonaID != "profile-actor" {
		t.Fatalf("facade requests=%+v", reader.requests)
	}
}

type recordingActivityReader struct {
	requests []activityports.PageRequest
}

func (reader *recordingActivityReader) List(
	_ context.Context,
	request activityports.PageRequest,
) (activityports.Page, error) {
	reader.requests = append(reader.requests, request)
	return activityports.Page{Items: []activitymodel.Activity{{
		OwnerPersonaID:  request.OwnerPersonaID,
		ActivityID:      "activity-" + request.Direction,
		ActivityType:    request.ActivityType,
		Direction:       request.Direction,
		Active:          true,
		ActorPersonaID:  "profile-actor",
		TargetPersonaID: request.OwnerPersonaID,
		TargetContentID: "post-profile",
		OccurredAt:      time.Date(2026, 8, 6, 1, 2, 3, 0, time.UTC),
	}}}, nil
}

func (*recordingActivityReader) CanAppendReadFact(
	context.Context,
	string,
	string,
) (bool, error) {
	return true, nil
}

var _ activityports.ActivityReader = (*recordingActivityReader)(nil)
