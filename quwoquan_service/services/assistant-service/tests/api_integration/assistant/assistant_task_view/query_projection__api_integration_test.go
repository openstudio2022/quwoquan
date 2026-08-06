// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// readiness_case: list-assistant-tasks-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	taskhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/adapters/inbound/http"
	taskapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/application"
	taskmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/domain/model"
	taskpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/infrastructure/persistence"
)

func TestAssistantTaskViewFiltersAndOrdersTheTrustedAccountsProjection(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "assistant_task_view_api_integration")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	now := time.Now().UTC().Truncate(time.Millisecond)
	_, err = runtime.Database.Collection("rm_assistant_tasks").InsertMany(startupCtx, []any{
		bson.M{"accountId": "task-owner", "taskId": "task-old", "title": "old", "status": "open", "updatedAt": now.Add(-time.Minute)},
		bson.M{"accountId": "task-owner", "taskId": "task-new", "title": "new", "status": "open", "updatedAt": now},
		bson.M{"accountId": "task-owner", "taskId": "task-done", "title": "done", "status": "done", "updatedAt": now.Add(time.Minute)},
		bson.M{"accountId": "task-other", "taskId": "task-secret", "title": "secret", "status": "open", "updatedAt": now.Add(2 * time.Minute)},
	})
	if err != nil {
		t.Fatalf("seed task projections: %v", err)
	}

	mux := http.NewServeMux()
	taskhttp.NewHandler(taskapplication.NewQueryFacade(
		taskpersistence.NewMongoReader(runtime.Database),
	)).RegisterRoutes(mux)

	request := httptest.NewRequest(http.MethodGet, "/assistant/tasks?status=open&limit=2", nil)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "task-owner", PersonaID: "task-owner:persona"},
	}))
	recorder := httptest.NewRecorder()
	mux.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("task query status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var view taskmodel.Slice
	if err := json.Unmarshal(recorder.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode task view: %v", err)
	}
	if len(view.Items) != 2 || view.Items[0].TaskID != "task-new" || view.Items[1].TaskID != "task-old" {
		t.Fatalf("unexpected filtered ordering: %+v", view.Items)
	}
	for _, item := range view.Items {
		if item.AccountID != "" || item.TaskID == "task-secret" || item.Status != "open" {
			t.Fatalf("task projection leaked or ignored filter: %+v", item)
		}
	}

	unauthorized := httptest.NewRecorder()
	mux.ServeHTTP(unauthorized, httptest.NewRequest(http.MethodGet, "/assistant/tasks", nil))
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("untrusted request status=%d body=%s", unauthorized.Code, unauthorized.Body.String())
	}
}
