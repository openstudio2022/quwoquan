package recommendation

import (
	"context"
	"testing"
)

func TestHotPathHasAcceptedEventReadsAcceptReceiptWithoutMutatingIt(t *testing.T) {
	ctx := context.Background()
	hotPath := NewHotPath(newMockRedis())

	accepted, err := hotPath.HasAcceptedEvent(ctx, "user-1", "event-1")
	if err != nil {
		t.Fatalf("read absent receipt: %v", err)
	}
	if accepted {
		t.Fatal("absent receipt must not be accepted")
	}

	created, err := hotPath.AcceptEvent(ctx, BehaviorSignal{
		UserID: "user-1", ClientEventID: "event-1",
	})
	if err != nil || !created {
		t.Fatalf("create receipt = accepted:%v err:%v, want true/nil", created, err)
	}

	accepted, err = hotPath.HasAcceptedEvent(ctx, "user-1", "event-1")
	if err != nil {
		t.Fatalf("read accepted receipt: %v", err)
	}
	if !accepted {
		t.Fatal("accepted receipt must remain visible to a replay")
	}
}
