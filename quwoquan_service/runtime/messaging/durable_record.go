package runtimemessaging

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"
)

// DurableRecordAppender is the minimal transport boundary required by an
// object-owned stream publisher. Domain adapters keep stream names and event
// schemas local while this helper centralizes deterministic field ordering and
// bounded retention.
type DurableRecordAppender interface {
	AppendDurable(context.Context, DurableMessage) (string, error)
	SetDurableRetention(context.Context, string, time.Duration) error
}

func DurableFieldsFromMap(values map[string]string) []DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, DurableField{Name: key, Value: values[key]})
	}
	return fields
}

func DurableFieldMap(fields []DurableField) map[string]string {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[strings.TrimSpace(field.Name)] = field.Value
	}
	return values
}

func AppendDurableRecord(
	ctx context.Context,
	transport DurableRecordAppender,
	stream string,
	values map[string]string,
	retention time.Duration,
) error {
	stream = strings.TrimSpace(stream)
	if transport == nil {
		return fmt.Errorf("durable message transport is not configured")
	}
	if stream == "" {
		return fmt.Errorf("durable stream is required")
	}
	if retention <= 0 {
		return fmt.Errorf("durable stream retention must be positive")
	}
	if _, err := transport.AppendDurable(ctx, DurableMessage{
		Stream: stream,
		Fields: DurableFieldsFromMap(values),
	}); err != nil {
		return err
	}
	return transport.SetDurableRetention(ctx, stream, retention)
}
