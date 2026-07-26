package messaging

import (
	"context"
	"fmt"
	"sort"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

type durableStreamTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

func appendEntityDurableRecord(
	ctx context.Context,
	transport durableStreamTransport,
	stream string,
	values map[string]string,
	retention time.Duration,
) error {
	if transport == nil {
		return fmt.Errorf("durable message transport is not configured")
	}
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
	if _, err := transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: stream,
		Fields: fields,
	}); err != nil {
		return err
	}
	return transport.SetDurableRetention(ctx, stream, retention)
}
