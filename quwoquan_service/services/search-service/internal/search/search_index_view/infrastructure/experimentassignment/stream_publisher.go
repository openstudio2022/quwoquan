package experimentassignment

import (
	"context"
	"crypto/sha256"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

const (
	StreamName      = "events.ops.experiment_assignment_observed"
	StreamRetention = 7 * 24 * time.Hour
)

type Transport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

type Publisher struct {
	transport Transport
}

func NewPublisher(transport Transport) (*Publisher, error) {
	if transport == nil {
		return nil, fmt.Errorf("search experiment assignment publisher requires message transport")
	}
	return &Publisher{transport: transport}, nil
}

func (p *Publisher) PublishExperimentAssignment(
	ctx context.Context,
	observation application.AssignmentObservation,
) error {
	identity := strings.Join([]string{
		observation.ExperimentID,
		strconv.FormatInt(observation.ExperimentRevision, 10),
		observation.SubjectKey,
	}, "\x00")
	eventID := fmt.Sprintf("search-experiment-assignment-%x", sha256.Sum256([]byte(identity)))
	values := map[string]string{
		"eventId": eventID, "eventType": "ExperimentAssignmentObserved",
		"producer": "search-service", "experimentId": observation.ExperimentID,
		"experimentRevision": strconv.FormatInt(observation.ExperimentRevision, 10),
		"subjectKey":         observation.SubjectKey, "variant": observation.Variant,
		"assignedAt": observation.AssignedAt.UTC().Format(time.RFC3339Nano),
	}
	if _, err := p.transport.AppendDurable(ctx, runtimemessaging.DurableMessage{
		Stream: StreamName, Fields: fields(values),
	}); err != nil {
		return err
	}
	return p.transport.SetDurableRetention(ctx, StreamName, StreamRetention)
}

func fields(values map[string]string) []runtimemessaging.DurableField {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	result := make([]runtimemessaging.DurableField, 0, len(keys))
	for _, key := range keys {
		result = append(result, runtimemessaging.DurableField{Name: key, Value: values[key]})
	}
	return result
}

var _ application.AssignmentObservationPublisher = (*Publisher)(nil)
