package application

import (
	"context"
	"fmt"
	"sync"
	"testing"
)

// recordingNotificationCommandWriter is a local-contract spy, not a runtime
// Notification implementation. It records only Assistant's outbound command
// seam and intentionally exposes no lifecycle/query/storage behavior.
type recordingNotificationCommandWriter struct {
	mu       sync.Mutex
	commands []NotificationAppMessageCommand
}

func TestRecordingNotificationCommandWriterKeepsTypedUserBoundary(t *testing.T) {
	t.Parallel()

	writer := newRecordingNotificationCommandWriter()
	first, err := writer.CreateAppMessage(context.Background(), NotificationAppMessageCommand{
		IdempotencyKey: "assistant-notification-user-a",
		UserID:         "user-a",
		MessageType:    "assistant",
		Source:         "assistant_turn",
		SourceID:       "turn-a",
	})
	if err != nil {
		t.Fatalf("CreateAppMessage(user-a): %v", err)
	}
	second, err := writer.CreateAppMessage(context.Background(), NotificationAppMessageCommand{
		IdempotencyKey: "assistant-notification-user-b",
		UserID:         "user-b",
		MessageType:    "assistant",
		Source:         "assistant_turn",
		SourceID:       "turn-b",
	})
	if err != nil {
		t.Fatalf("CreateAppMessage(user-b): %v", err)
	}
	if first.MessageID == "" || second.MessageID == "" || first.MessageID == second.MessageID {
		t.Fatalf("receipts must carry distinct Notification-owned IDs: first=%q second=%q", first.MessageID, second.MessageID)
	}

	commands := writer.CommandsForUser("user-a")
	if len(commands) != 1 {
		t.Fatalf("CommandsForUser(user-a)=%d, want 1", len(commands))
	}
	if commands[0].UserID != "user-a" || commands[0].SourceID != "turn-a" {
		t.Fatalf("CommandsForUser(user-a) leaked another actor: %+v", commands[0])
	}
}

func newRecordingNotificationCommandWriter() *recordingNotificationCommandWriter {
	return &recordingNotificationCommandWriter{}
}

func (w *recordingNotificationCommandWriter) CreateAppMessage(
	_ context.Context,
	command NotificationAppMessageCommand,
) (NotificationAppMessageReceipt, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.commands = append(w.commands, command)
	return NotificationAppMessageReceipt{
		MessageID: fmt.Sprintf("notification-test-%d", len(w.commands)),
	}, nil
}

func (w *recordingNotificationCommandWriter) CommandsForUser(
	userID string,
) []NotificationAppMessageCommand {
	w.mu.Lock()
	defer w.mu.Unlock()
	out := make([]NotificationAppMessageCommand, 0, len(w.commands))
	for _, command := range w.commands {
		if command.UserID == userID {
			out = append(out, command)
		}
	}
	return out
}
