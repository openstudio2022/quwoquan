// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package assistant_task_view_test

import (
	"context"
	"testing"

	taskapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/application"
	taskmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/domain/model"
)

type taskReader struct {
	status string
	limit  int
}

func (reader *taskReader) List(_ context.Context, _ string, status string, limit int) ([]taskmodel.Item, error) {
	reader.status, reader.limit = status, limit
	return nil, nil
}

func TestTaskViewNormalizesFilterAndReturnsTypedEmptySlice(t *testing.T) {
	reader := &taskReader{}
	view, err := taskapplication.NewQueryFacade(reader).
		ListTasks(t.Context(), "account-1", " pending ", 1000)
	if err != nil {
		t.Fatal(err)
	}
	if reader.status != "pending" || reader.limit != 100 || view.Items == nil || len(view.Items) != 0 {
		t.Fatalf("status=%q limit=%d view=%+v", reader.status, reader.limit, view)
	}
}
