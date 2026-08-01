package assistantturnview_test

import (
	"context"
	"testing"

	turnviewapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/application"
	turnviewmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/domain/model"
)

type recordingReader struct {
	userID    string
	sessionID string
	limit     int
	cursor    string
	result    turnviewmodel.AssistantTurnListView
}

func (r *recordingReader) ListSessionTurns(
	_ context.Context,
	userID string,
	sessionID string,
	limit int,
	cursor string,
) (turnviewmodel.AssistantTurnListView, error) {
	r.userID = userID
	r.sessionID = sessionID
	r.limit = limit
	r.cursor = cursor
	return r.result, nil
}

// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#sit-001
func TestQueryFacadeOwnsAndNormalizesSessionTurnHistoryRead(t *testing.T) {
	reader := &recordingReader{result: turnviewmodel.AssistantTurnListView{
		Items: []turnviewmodel.AssistantTurnSummaryView{{TurnID: "turn_1"}},
	}}
	facade := turnviewapplication.NewQueryFacade(reader)

	result, err := facade.ListSessionTurns(
		context.Background(),
		" user_1 ",
		" session_1 ",
		101,
		" cursor_1 ",
	)
	if err != nil {
		t.Fatalf("ListSessionTurns() error = %v", err)
	}
	if reader.userID != "user_1" || reader.sessionID != "session_1" {
		t.Fatalf(
			"normalized owner = (%q, %q)",
			reader.userID,
			reader.sessionID,
		)
	}
	if reader.limit != 50 || reader.cursor != "cursor_1" {
		t.Fatalf("normalized page = (limit=%d, cursor=%q)", reader.limit, reader.cursor)
	}
	if len(result.Items) != 1 || result.Items[0].TurnID != "turn_1" {
		t.Fatalf("result = %+v", result)
	}
}
