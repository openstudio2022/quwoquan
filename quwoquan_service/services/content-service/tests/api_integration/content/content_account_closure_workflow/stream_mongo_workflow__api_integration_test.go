// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// readiness_case: recover-content-account-closure-dead-letter-api
package content_account_closure_workflow_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	closurehttp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/adapters/inbound/http"
	closurestream "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/adapters/inbound/stream"
	closureapp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/application"
	closuremodel "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/domain/model"
	"quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"
)

type acceptingDeletionFence struct{}

func (acceptingDeletionFence) ClaimUnreferencedDeletion(context.Context, string, string) (bool, error) {
	return true, nil
}

func (acceptingDeletionFence) MarkWorkDeleted(context.Context, string) error { return nil }

type successfulCacheCleaner struct{}

func (successfulCacheCleaner) BlockClosedSubjects(context.Context, []string) error     { return nil }
func (successfulCacheCleaner) DeletePersonalCacheKeys(context.Context, []string) error { return nil }
func (successfulCacheCleaner) VerifyNoPersonalDataResidual(context.Context, []string, []string) error {
	return nil
}

type successfulSearchDeleter struct{}

func (successfulSearchDeleter) DeleteSearchDocument(
	context.Context,
	accountclosure.SearchDocumentID,
) error {
	return nil
}

type successfulMediaReclaimer struct{}

func (successfulMediaReclaimer) ReclaimMediaArtifacts(
	context.Context,
	[]string,
	[]string,
	[]string,
	[]string,
) error {
	return nil
}

func TestTypedStreamIngressConvergesObjectOwnedMongoWorkflow(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "content_account_closure_workflow")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	digestor, err := accountclosure.NewHMACSubjectDigestor("account-closure-api-integration-secret")
	if err != nil {
		t.Fatalf("create subject digestor: %v", err)
	}
	store, err := accountclosure.NewMongoStore(runtime.Database, digestor, acceptingDeletionFence{})
	if err != nil {
		t.Fatalf("create workflow store: %v", err)
	}
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure workflow indexes: %v", err)
	}
	processor, err := accountclosure.NewProcessor(
		store,
		successfulCacheCleaner{},
		successfulSearchDeleter{},
		successfulMediaReclaimer{},
	)
	if err != nil {
		t.Fatalf("create workflow processor: %v", err)
	}
	handler := closurestream.NewHandler(closureapp.NewIngress(processor))
	occurredAt := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
	event := closuremodel.UserAccountClosedEvent{
		EventID:        "account-closed-typed-stream",
		EventName:      closuremodel.UserAccountClosedName,
		AccountID:      "account-closed",
		AccountVersion: 7,
		Payload: closuremodel.UserAccountClosedPayload{
			UserID:       "account-closed",
			PersonaIDs:   []string{"persona-closed"},
			AccountState: "closed",
			UpdatedAt:    occurredAt,
		},
		OccurredAt: occurredAt,
	}
	first, err := handler.Apply(context.Background(), event)
	if err != nil || first.Replayed {
		t.Fatalf("first workflow result=%#v err=%v", first, err)
	}
	replay, err := handler.Apply(context.Background(), event)
	if err != nil || !replay.Replayed {
		t.Fatalf("replayed workflow result=%#v err=%v", replay, err)
	}
	count, err := runtime.Database.Collection(accountclosure.InboxCollection).CountDocuments(
		context.Background(),
		bson.M{"_id": event.EventID, "state": accountclosure.WorkflowStateCompleted},
	)
	if err != nil || count != 1 {
		t.Fatalf("completed workflow count=%d err=%v", count, err)
	}
}

func TestRecoveryHTTPReleasesObjectOwnedTerminalMarkerInRealMongo(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(
		context.Background(),
		"content_account_closure_recovery",
	)
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	digestor, err := accountclosure.NewHMACSubjectDigestor(
		"account-closure-recovery-api-integration-secret",
	)
	if err != nil {
		t.Fatalf("create subject digestor: %v", err)
	}
	store, err := accountclosure.NewMongoStore(
		runtime.Database,
		digestor,
		acceptingDeletionFence{},
	)
	if err != nil {
		t.Fatalf("create workflow store: %v", err)
	}
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure workflow indexes: %v", err)
	}
	processor, err := accountclosure.NewProcessor(
		store,
		successfulCacheCleaner{},
		successfulSearchDeleter{},
		successfulMediaReclaimer{},
	)
	if err != nil {
		t.Fatalf("create workflow processor: %v", err)
	}
	redisRuntime, err := testinfra.StartRealRedis(context.Background())
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := redisRuntime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})
	if err := redisRuntime.FlushDBs(context.Background(), 0); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	redisRouter := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     "standalone",
				Addr:     redisRuntime.Addr,
				Password: redisRuntime.Password,
				DB:       0,
				TLS:      redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		if closeErr := redisRouter.Close(); closeErr != nil {
			t.Errorf("close real Redis router: %v", closeErr)
		}
	})
	consumer, err := accountclosure.NewConsumer(
		redisRouter.Scene("general"),
		processor,
		store,
		"content-account-closure-recovery-api",
		nil,
		accountclosure.ConsumerConfig{},
	)
	if err != nil {
		t.Fatalf("create account-closure consumer: %v", err)
	}
	const sourceStreamID = "1700000000000-0"
	if _, err := store.RecordFailure(
		context.Background(),
		accountclosure.UserAccountEventStream,
		sourceStreamID,
		"event-account-closure-recovery",
		errors.New("terminal test failure"),
	); err != nil {
		t.Fatalf("record terminal failure: %v", err)
	}
	if err := store.MarkDeadLettered(
		context.Background(),
		accountclosure.UserAccountEventStream,
		sourceStreamID,
	); err != nil {
		t.Fatalf("mark terminal failure: %v", err)
	}
	commands, err := closureapp.NewContentAccountClosureRecoveryCommandFacet(consumer)
	if err != nil {
		t.Fatalf("build recovery commands: %v", err)
	}
	recoveryHandler, err := closurehttp.NewHandler(commands)
	if err != nil {
		t.Fatalf("build recovery handler: %v", err)
	}
	handler, err := recoveryHandler.Mount(http.NotFoundHandler())
	if err != nil {
		t.Fatalf("build recovery route: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/account-closure/dead-letters:recover",
		strings.NewReader(`{"sourceStreamId":"`+sourceStreamID+`"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "recover-content-account-closure-once")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("recovery status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	deadLettered, err := store.IsDeadLettered(
		context.Background(),
		accountclosure.UserAccountEventStream,
		sourceStreamID,
	)
	if err != nil {
		t.Fatalf("read terminal marker after recovery: %v", err)
	}
	if deadLettered {
		t.Fatal("recovery must clear the object-owned terminal marker")
	}
}
