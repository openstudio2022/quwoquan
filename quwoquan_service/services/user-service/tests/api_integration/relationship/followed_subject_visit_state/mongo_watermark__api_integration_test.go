// readiness_case: mark-followed-subject-visited-api
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
package api_integration

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	visithttp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/adapters/inbound/http"
	visitapp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/application"
	visitpersistence "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

type fixedVisitActorResolver string

func (r fixedVisitActorResolver) ResolveActorPersonaID(
	context.Context,
	*http.Request,
	string,
) (string, error) {
	return string(r), nil
}

func TestFollowedSubjectVisitStateMongoWatermarkAndReceipt(t *testing.T) {
	usersupport.WithUserMongo(t, func(ctx context.Context, runtime *testinfra.RealMongo) {
		store := visitpersistence.NewMongoFollowedSubjectVisitStore(runtime.Database)
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatalf("ensure visit state indexes: %v", err)
		}
		service := visitapp.NewVisitService(store)
		visitedAt := time.Now().UTC().Truncate(time.Millisecond)
		input := visitapp.MarkVisitedInput{
			PersonaID: "persona-viewer", SubjectType: "homepage", SubjectID: "homepage-1",
			VisitedAt: visitedAt, ClientRequestID: "visit-request-1",
		}
		first, err := service.MarkVisited(ctx, input)
		if err != nil {
			t.Fatalf("mark visited: %v", err)
		}
		replayed, err := service.MarkVisited(ctx, input)
		if err != nil || !replayed.Replayed || !replayed.LastVisitedAt.Equal(first.LastVisitedAt) {
			t.Fatalf("visit receipt replay drifted: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		older := input
		older.ClientRequestID, older.VisitedAt = "visit-request-2", visitedAt.Add(-time.Hour)
		result, err := service.MarkVisited(ctx, older)
		if err != nil || !result.LastVisitedAt.Equal(first.LastVisitedAt) {
			t.Fatalf("visit watermark regressed: result=%+v err=%v", result, err)
		}

		mux := http.NewServeMux()
		visithttp.NewHandler(service, fixedVisitActorResolver("persona-viewer")).RegisterRoutes(mux)
		request := httptest.NewRequest(
			http.MethodPost,
			"/user/followed-subjects/homepage/homepage-2:mark-visited",
			bytes.NewBufferString(`{"visitedAt":"`+visitedAt.Format(time.RFC3339)+`","clientRequestId":"visit-http-1"}`),
		)
		request.Header.Set("Content-Type", "application/json")
		response := httptest.NewRecorder()
		mux.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("production mark-visited HTTP status=%d body=%s", response.Code, response.Body.String())
		}
		stored, err := runtime.Database.Collection("followed_subject_visit_states").CountDocuments(
			ctx,
			map[string]any{
				"personaId":   "persona-viewer",
				"subjectType": "homepage",
				"subjectId":   "homepage-2",
			},
		)
		if err != nil || stored != 1 {
			t.Fatalf("production HTTP did not persist canonical visit state: count=%d err=%v", stored, err)
		}
	})
}
