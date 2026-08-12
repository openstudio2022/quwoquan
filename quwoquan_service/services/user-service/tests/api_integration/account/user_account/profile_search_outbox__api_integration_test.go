// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-snapshot-versioning/spec.md#gwt-002
package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/profileprojection"
)

type switchableProfileSearchTransport struct {
	runtimemessaging.MessageTransport
	available bool
	attempts  int
	appended  int
}

func (transport *switchableProfileSearchTransport) AppendDurable(
	ctx context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	transport.attempts++
	if !transport.available {
		return "", fmt.Errorf("durable profile projection stream unavailable")
	}
	id, err := transport.MessageTransport.AppendDurable(ctx, message)
	if err == nil {
		transport.appended++
	}
	return id, err
}

func TestProfileSearchProjectionOutboxRetriesStreamFailureWithoutLosingProfileUpdate(
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

	redis := rtredis.NewMemoryClient()
	baseTransport, err := runtimemessaging.NewRedisMessageTransport(redis, redis)
	if err != nil {
		t.Fatalf("build durable transport: %v", err)
	}
	streamTransport := &switchableProfileSearchTransport{MessageTransport: baseTransport}
	streamPublisher, err := profileprojection.NewStreamPublisher(streamTransport)
	if err != nil {
		t.Fatalf("build UserProfile search stream publisher: %v", err)
	}
	outboxStore, err := useraccountpersistence.NewUserProfileSearchOutboxStore(pgPool)
	if err != nil {
		t.Fatalf("create UserProfile search outbox store: %v", err)
	}
	relay, err := useraccountapp.NewUserProfileSearchOutboxRelay(
		outboxStore,
		streamPublisher,
		"profile-search-api-integration",
	)
	if err != nil {
		t.Fatalf("create UserProfile search relay: %v", err)
	}

	if didWork, err := relay.RelayOnce(context.Background()); !didWork || err == nil {
		t.Fatalf("stream outage must leave a retryable checkpoint: didWork=%v err=%v", didWork, err)
	}
	var failedPending int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM user_profile_search_outbox
		 WHERE user_id=$1
		   AND published_at IS NULL
		   AND last_failure_code='stream_publish'
		   AND last_failure_digest <> ''`,
		ownerID,
	).Scan(&failedPending); err != nil {
		t.Fatalf("inspect failed profile search checkpoint: %v", err)
	}
	if failedPending != 1 {
		t.Fatalf("expected one persisted failed checkpoint, got %d", failedPending)
	}

	streamTransport.available = true
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
		t.Fatalf("durable append success must advance every profile search checkpoint, pending=%d", unpublishedEvents)
	}
	if streamTransport.attempts != 3 || streamTransport.appended != 2 {
		t.Fatalf("expected one failed attempt plus two durable appends, attempts=%d appended=%d", streamTransport.attempts, streamTransport.appended)
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

func TestPersonaProfileProjectionAdvancesBeyondRetainedSearchOutboxHistory(
	t *testing.T,
) {
	t.Cleanup(func() { cleanAll(t) })
	const (
		ownerID                = "retained_search_history_owner"
		retainedProfileVersion = int64(18)
	)
	personaID := createProfileUpdateFixture(t, ownerID, "retained_history")

	for profileVersion := int64(2); profileVersion <= retainedProfileVersion; profileVersion++ {
		if _, err := pgPool.Exec(
			context.Background(),
			`INSERT INTO user_profile_search_outbox (
				event_id, user_id, profile_version, event_type, payload_json, occurred_at,
				published_at, next_attempt_at
			) VALUES ($1, $2, $3, 'UserProfileUpdated', $4::jsonb, NOW(), NOW(), NOW())`,
			fmt.Sprintf("retained-profile-search-%02d", profileVersion),
			ownerID,
			profileVersion,
			fmt.Sprintf(`{"eventId":"retained-profile-search-%02d","userId":%q,"profileVersion":%d,"operation":"upsert","nickname":"retained","avatarUrl":"","bio":"","identityTags":[],"followerCount":0,"postCount":0,"updatedAt":"2026-08-12T00:00:00Z"}`, profileVersion, ownerID, profileVersion),
		); err != nil {
			t.Fatalf("seed retained profile search version %d: %v", profileVersion, err)
		}
	}

	update := doRequest(
		t,
		http.MethodPatch,
		"/user/profile",
		`{"nickname":"retained_history_updated"}`,
		authHeadersForPersona(ownerID, personaID),
	)
	if update.Code != http.StatusOK {
		t.Fatalf("profile update: expected 200, got %d: %s", update.Code, update.Body.String())
	}

	var materializedProfileVersion int64
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT profile_version FROM user_profiles WHERE user_id=$1`,
		ownerID,
	).Scan(&materializedProfileVersion); err != nil {
		t.Fatalf("read materialized profile version: %v", err)
	}
	if materializedProfileVersion != retainedProfileVersion+1 {
		t.Fatalf(
			"profile projection must advance beyond retained outbox history: got=%d want=%d",
			materializedProfileVersion,
			retainedProfileVersion+1,
		)
	}

	var pendingCurrentVersion int
	if err := pgPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*)
		 FROM user_profile_search_outbox
		 WHERE user_id=$1
		   AND profile_version=$2
		   AND event_type='UserProfileUpdated'
		   AND published_at IS NULL`,
		ownerID,
		retainedProfileVersion+1,
	).Scan(&pendingCurrentVersion); err != nil {
		t.Fatalf("read current profile search projection coordinate: %v", err)
	}
	if pendingCurrentVersion != 1 {
		t.Fatalf(
			"expected one durable search coordinate above retained history, got %d",
			pendingCurrentVersion,
		)
	}
}
