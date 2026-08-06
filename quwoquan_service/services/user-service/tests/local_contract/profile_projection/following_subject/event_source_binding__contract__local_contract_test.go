// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: project-following-subject-local
package local_contract

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	followingevent "quwoquan_service/services/user-service/internal/profile_projection/following_subject/adapters/inbound/event"
	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
)

func TestFollowingSubjectProjectionDeclaresComposedProductionStreams(t *testing.T) {
	_, source, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	raw, err := os.ReadFile(filepath.Join(root, "contracts/profile_projection/following_subject/object.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Lifecycle struct {
			SourceEvents   []string `yaml:"source_events"`
			EventConsumers []struct {
				Name        string `yaml:"name"`
				Kind        string `yaml:"kind"`
				Facet       string `yaml:"facet"`
				Method      string `yaml:"method"`
				Idempotency string `yaml:"idempotency"`
			} `yaml:"event_consumers"`
		} `yaml:"lifecycle"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	want := []string{
		"user.persona_relationship.PersonaFollowStateChanged",
		"user.persona_relationship.PersonaBlocked",
		"user.persona_relationship.PersonaUnblocked",
		"user.subject_follow.SubjectFollowStateChanged",
		"user.followed_subject_visit_state.FollowedSubjectVisited",
		"user.user_account.UserAccountClosed",
	}
	if len(document.Lifecycle.EventConsumers) != 1 ||
		document.Lifecycle.EventConsumers[0].Name != "ProjectFollowingSubject" ||
		document.Lifecycle.EventConsumers[0].Kind != "projector" ||
		document.Lifecycle.EventConsumers[0].Facet != "FollowingSubjectProjector" ||
		document.Lifecycle.EventConsumers[0].Method != "apply" ||
		document.Lifecycle.EventConsumers[0].Idempotency != "aggregate_version" ||
		!reflect.DeepEqual(document.Lifecycle.SourceEvents, want) {
		t.Fatalf("following subject lifecycle event binding drifted: %+v", document.Lifecycle)
	}

	store := &followingSubjectProjectionStore{}
	handler := followingevent.NewHandler(
		followingapp.NewFollowingSubjectProjector(store),
	)
	occurredAt := time.Date(2026, time.August, 6, 2, 0, 0, 0, time.UTC)
	if err := handler.Apply(t.Context(), followingapp.FollowChangedEvent{
		EventID:         "following-subject-contract-7",
		ViewerPersonaID: "persona-viewer",
		SubjectType:     "persona",
		SubjectID:       "persona-subject",
		Following:       true,
		OccurredAt:      occurredAt,
		SourceVersion:   7,
	}); err != nil {
		t.Fatalf("apply production FollowingSubject handler: %v", err)
	}
	if store.upserts != 1 || store.personaID != "persona-viewer" ||
		store.subjectType != "persona" || store.subjectID != "persona-subject" ||
		store.version != 7 || !store.occurredAt.Equal(occurredAt) {
		t.Fatalf("production FollowingSubject state=%+v", store)
	}
}

type followingSubjectProjectionStore struct {
	upserts     int
	personaID   string
	subjectType string
	subjectID   string
	version     int64
	occurredAt  time.Time
}

func (store *followingSubjectProjectionStore) UpsertFollow(
	_ context.Context,
	personaID string,
	subjectType string,
	subjectID string,
	occurredAt time.Time,
	sourceVersion int64,
) error {
	store.upserts++
	store.personaID = personaID
	store.subjectType = subjectType
	store.subjectID = subjectID
	store.version = sourceVersion
	store.occurredAt = occurredAt
	return nil
}

func (*followingSubjectProjectionStore) RemoveFollow(
	context.Context,
	string,
	string,
	string,
	int64,
) error {
	return nil
}
