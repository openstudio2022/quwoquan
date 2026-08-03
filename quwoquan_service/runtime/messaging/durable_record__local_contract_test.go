package runtimemessaging

import (
	"context"
	"errors"
	"testing"
	"time"
)

type durableRecordAppenderSpy struct {
	message   DurableMessage
	retention time.Duration
	appendErr error
}

func (spy *durableRecordAppenderSpy) AppendDurable(
	_ context.Context,
	message DurableMessage,
) (string, error) {
	spy.message = message
	return "1-0", spy.appendErr
}

func (spy *durableRecordAppenderSpy) SetDurableRetention(
	_ context.Context,
	_ string,
	retention time.Duration,
) error {
	spy.retention = retention
	return nil
}

func TestAppendDurableRecordOrdersFieldsAndBoundsRetention(t *testing.T) {
	spy := &durableRecordAppenderSpy{}
	if err := AppendDurableRecord(
		context.Background(),
		spy,
		"events.circle.post_placements",
		map[string]string{"z": "last", "a": "first"},
		7*24*time.Hour,
	); err != nil {
		t.Fatal(err)
	}
	if spy.message.Stream != "events.circle.post_placements" ||
		len(spy.message.Fields) != 2 ||
		spy.message.Fields[0].Name != "a" ||
		spy.message.Fields[1].Name != "z" {
		t.Fatalf("durable record drift: %#v", spy.message)
	}
	if spy.retention != 7*24*time.Hour {
		t.Fatalf("retention=%s", spy.retention)
	}

	spy.appendErr = errors.New("append unavailable")
	spy.retention = 0
	if err := AppendDurableRecord(
		context.Background(), spy, "events.test", nil, time.Hour,
	); err == nil || spy.retention != 0 {
		t.Fatalf("append failure must stop retention err=%v retention=%s", err, spy.retention)
	}
}
