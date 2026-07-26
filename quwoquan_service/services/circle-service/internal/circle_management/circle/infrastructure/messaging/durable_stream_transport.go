package messaging

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

// durableStreamTransport keeps object-owned stream names in this package while
// routing durable delivery through the preflighted runtime transport.
type durableStreamTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

func appendCircleDurableRecord(
	ctx context.Context,
	transport durableStreamTransport,
	stream string,
	values map[string]string,
	retention time.Duration,
) error {
	if transport == nil {
		return fmt.Errorf("durable message transport is not configured")
	}
	if _, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: stream,
		Fields: durableFieldsFromValues(values),
	}); err != nil {
		return err
	}
	return transport.SetDurableRetention(ctx, stream, retention)
}

func durableFieldsFromValues(values map[string]string) []runtimemessaging.DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	fields := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		fields = append(fields, runtimemessaging.DurableField{
			Name: key, Value: values[key],
		})
	}
	return fields
}

func durableFieldValues(fields []runtimemessaging.DurableField) map[string]string {
	values := make(map[string]string, len(fields))
	for _, field := range fields {
		values[strings.TrimSpace(field.Name)] = field.Value
	}
	return values
}
