// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-snapshot-versioning/spec.md#gwt-002
package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/searchindex"
)

type switchableProfileSearchES struct {
	available bool
	paths     []string
}

func (server *switchableProfileSearchES) handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		server.paths = append(server.paths, r.Method+" "+r.URL.Path)
		if !server.available {
			http.Error(w, "search cluster unavailable", http.StatusServiceUnavailable)
			return
		}
		if r.Method != http.MethodPut ||
			!strings.HasPrefix(r.URL.Path, "/quwoquan_objects/_doc/") {
			http.Error(w, "unexpected search request", http.StatusTeapot)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"result":"created"}`))
	})
}

func TestProfileSearchProjectionOutboxRetriesESFailureWithoutLosingProfileUpdate(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })
	const ownerID = "profile_search_projection_owner"
	personaID := createProfileUpdateFixture(t, ownerID, "search_projection")

	update := doRequest(
		t,
		http.MethodPatch,
		"/user/profile",
		`{"nickname":"search_projection_updated","avatarAssetId":"ua_profile_search_projection","avatarUrl":"https://cdn.example.com/profile-search-updated.png"}`,
		authHeadersForPersona(ownerID, personaID),
	)
	if update.Code != http.StatusOK {
		t.Fatalf("profile update: expected 200, got %d: %s", update.Code, update.Body.String())
	}

	var (
		nickname          string
		unpublishedEvents int
		avatarEventCount  int
		profileEventCount int
	)
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT nickname FROM user_profiles WHERE user_id=$1`,
		ownerID,
	).Scan(&nickname); err != nil {
		t.Fatalf("read committed profile: %v", err)
	}
	if nickname != "search_projection_updated" {
		t.Fatalf("profile fact was not committed before ES relay: %q", nickname)
	}
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM user_profile_search_outbox
		 WHERE user_id=$1 AND published_at IS NULL`,
		ownerID,
	).Scan(&unpublishedEvents); err != nil {
		t.Fatalf("count pending profile search events: %v", err)
	}
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM user_profile_search_outbox
		 WHERE user_id=$1 AND event_type='UserAvatarUpdated'`,
		ownerID,
	).Scan(&avatarEventCount); err != nil {
		t.Fatalf("count avatar search events: %v", err)
	}
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM user_profile_search_outbox
		 WHERE user_id=$1 AND event_type='UserProfileUpdated'`,
		ownerID,
	).Scan(&profileEventCount); err != nil {
		t.Fatalf("count profile search events: %v", err)
	}
	if unpublishedEvents != 2 || avatarEventCount != 1 || profileEventCount != 1 {
		t.Fatalf(
			"expected durable profile+avatar search coordinates, pending=%d avatar=%d profile=%d",
			unpublishedEvents,
			avatarEventCount,
			profileEventCount,
		)
	}

	esRuntime := &switchableProfileSearchES{}
	esServer := httptest.NewServer(esRuntime.handler())
	defer esServer.Close()
	built, err := searchindex.Build(
		searchindex.ESConfig{
			Enabled:          true,
			Endpoints:        []string{esServer.URL},
			Index:            "quwoquan_objects",
			RequestTimeoutMs: 500,
		},
		useraccountpersistence.NewPgProfileStore(pgPool),
	)
	if err != nil {
		t.Fatalf("build UserProfile search projection: %v", err)
	}
	outboxStore, err := useraccountpersistence.NewUserProfileSearchOutboxStore(pgPool)
	if err != nil {
		t.Fatalf("create UserProfile search outbox store: %v", err)
	}
	relay, err := useraccountapp.NewUserProfileSearchOutboxRelay(
		outboxStore,
		built.Projector,
		"profile-search-api-integration",
	)
	if err != nil {
		t.Fatalf("create UserProfile search relay: %v", err)
	}

	if didWork, err := relay.RelayOnce(context.Background()); !didWork || err == nil {
		t.Fatalf("ES outage must leave a retryable checkpoint: didWork=%v err=%v", didWork, err)
	}
	var failedPending int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM user_profile_search_outbox
		 WHERE user_id=$1
		   AND published_at IS NULL
		   AND last_failure_code='search_project'
		   AND last_failure_digest <> ''`,
		ownerID,
	).Scan(&failedPending); err != nil {
		t.Fatalf("inspect failed profile search checkpoint: %v", err)
	}
	if failedPending != 1 {
		t.Fatalf("expected one persisted failed checkpoint, got %d", failedPending)
	}

	esRuntime.available = true
	if _, err := pgPool.Exec(
		context.Background(),
		`UPDATE user_profile_search_outbox
		 SET next_attempt_at=NOW()
		 WHERE user_id=$1 AND published_at IS NULL`,
		ownerID,
	); err != nil {
		t.Fatalf("make retry checkpoint ready: %v", err)
	}
	for attempt := 0; attempt < 2; attempt++ {
		didWork, err := relay.RelayOnce(context.Background())
		if err != nil || !didWork {
			t.Fatalf("replay %d: didWork=%v err=%v", attempt, didWork, err)
		}
	}

	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM user_profile_search_outbox
		 WHERE user_id=$1 AND published_at IS NULL`,
		ownerID,
	).Scan(&unpublishedEvents); err != nil {
		t.Fatalf("count acknowledged profile search events: %v", err)
	}
	if unpublishedEvents != 0 {
		t.Fatalf("ES success must advance every profile search checkpoint, pending=%d", unpublishedEvents)
	}
	if len(esRuntime.paths) != 3 {
		t.Fatalf("expected one failed attempt plus two idempotent replays, got %#v", esRuntime.paths)
	}
}

func TestAnonymousRegistrationCreatesDurablePersonaProfileSearchProjectionCoordinate(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	login := doRequest(
		t,
		http.MethodPost,
		"/auth/login/anonymous",
		`{"installId":"profile-search-install","deviceFingerprintHash":"profile-search-fingerprint","platform":"ios","appVersion":"1.0.0"}`,
		nil,
	)
	if login.Code != http.StatusOK {
		t.Fatalf("anonymous registration: expected 200, got %d: %s", login.Code, login.Body.String())
	}
	ownerID, _ := parseJSON(t, login)["ownerId"].(string)
	if ownerID == "" {
		t.Fatal("anonymous registration did not return ownerId")
	}

	var (
		eventType      string
		profileVersion int64
		published      bool
	)
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT event_type, profile_version, published_at IS NOT NULL
		 FROM user_profile_search_outbox
		 WHERE user_id=$1`,
		ownerID,
	).Scan(&eventType, &profileVersion, &published); err != nil {
		t.Fatalf("read initial Persona profile search checkpoint: %v", err)
	}
	if eventType != "UserProfileUpdated" || profileVersion != 1 || published {
		t.Fatalf(
			"unexpected initial Persona profile search checkpoint: event=%q version=%d published=%v",
			eventType,
			profileVersion,
			published,
		)
	}
}
