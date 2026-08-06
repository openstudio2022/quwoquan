// readiness_case: follow-subject-api
// readiness_case: unfollow-subject-api
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
package api_integration

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	subjecthttp "quwoquan_service/services/user-service/internal/relationship/subject_follow/adapters/inbound/http"
	subjectapp "quwoquan_service/services/user-service/internal/relationship/subject_follow/application"
	subjectpersistence "quwoquan_service/services/user-service/internal/relationship/subject_follow/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

type fixedSubjectFollowActorResolver string

func (r fixedSubjectFollowActorResolver) ResolveActorPersonaID(
	context.Context,
	*http.Request,
	string,
) (string, error) {
	return string(r), nil
}

func TestSubjectFollowPostgresReplayAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		service := subjectapp.NewSubjectFollowService(subjectpersistence.NewPgSubjectFollowStore(pool))
		command := subjectapp.FollowSubjectCommand{
			PersonaID: "subject-viewer", SubjectType: "homepage", SubjectID: "homepage-1",
			Source: "homepage", IdempotencyKey: "subject-follow-key",
		}
		first, err := service.Follow(ctx, command)
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := service.Follow(ctx, command)
		if err != nil || !replayed.IdempotentReplay || replayed.Follow.Version != first.Follow.Version {
			t.Fatalf("SubjectFollow replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var outboxCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM subject_follow_outbox`).Scan(&outboxCount); err != nil || outboxCount != 1 {
			t.Fatalf("SubjectFollow outbox=%d err=%v", outboxCount, err)
		}

		mux := http.NewServeMux()
		subjecthttp.NewHandler(service, fixedSubjectFollowActorResolver("subject-viewer")).RegisterRoutes(mux)
		followRequest := httptest.NewRequest(
			http.MethodPost,
			"/relationships/subjects/homepage/homepage-2/follow",
			bytes.NewBufferString(`{"source":"homepage"}`),
		)
		followRequest.Header.Set("Content-Type", "application/json")
		followRequest.Header.Set("Idempotency-Key", "subject-follow-http")
		followResponse := httptest.NewRecorder()
		mux.ServeHTTP(followResponse, followRequest)
		if followResponse.Code != http.StatusOK {
			t.Fatalf("production FollowSubject HTTP status=%d body=%s", followResponse.Code, followResponse.Body.String())
		}

		unfollowRequest := httptest.NewRequest(
			http.MethodDelete,
			"/relationships/subjects/homepage/homepage-2/follow",
			nil,
		)
		unfollowRequest.Header.Set("Idempotency-Key", "subject-unfollow-http")
		unfollowResponse := httptest.NewRecorder()
		mux.ServeHTTP(unfollowResponse, unfollowRequest)
		if unfollowResponse.Code != http.StatusOK {
			t.Fatalf("production UnfollowSubject HTTP status=%d body=%s", unfollowResponse.Code, unfollowResponse.Body.String())
		}
		var state string
		if err := pool.QueryRow(
			ctx,
			`SELECT state FROM subject_follows WHERE persona_id=$1 AND subject_type=$2 AND subject_id=$3`,
			"subject-viewer",
			"homepage",
			"homepage-2",
		).Scan(&state); err != nil || state != "unfollowed" {
			t.Fatalf("production HTTP follow/unfollow state=%q err=%v", state, err)
		}
	})
}
