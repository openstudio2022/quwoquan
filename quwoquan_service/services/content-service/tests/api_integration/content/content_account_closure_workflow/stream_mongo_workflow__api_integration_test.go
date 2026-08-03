package content_account_closure_workflow_test

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
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
