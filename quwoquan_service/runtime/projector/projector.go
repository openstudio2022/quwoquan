package projector

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"quwoquan_service/runtime/eventstore"
)

// Projector consumes domain events and builds read models.
type Projector interface {
	Name() string
	EventTypes() []string
	Project(ctx context.Context, event eventstore.StoredEvent) error
}

// Dispatcher routes events to registered projectors.
type Dispatcher struct {
	mu          sync.RWMutex
	projectors  map[string][]Projector
	logger      *slog.Logger
}

func NewDispatcher(logger *slog.Logger) *Dispatcher {
	return &Dispatcher{
		projectors: make(map[string][]Projector),
		logger:     logger,
	}
}

// Register adds a projector to the dispatcher.
func (d *Dispatcher) Register(p Projector) {
	d.mu.Lock()
	defer d.mu.Unlock()

	for _, eventType := range p.EventTypes() {
		d.projectors[eventType] = append(d.projectors[eventType], p)
	}
	d.logger.Info("projector.registered",
		slog.String("projector", p.Name()),
		slog.Any("eventTypes", p.EventTypes()))
}

// Dispatch sends an event to all interested projectors.
func (d *Dispatcher) Dispatch(ctx context.Context, event eventstore.StoredEvent) error {
	d.mu.RLock()
	handlers := d.projectors[event.Type]
	d.mu.RUnlock()

	var errs []error
	for _, p := range handlers {
		start := time.Now()
		if err := p.Project(ctx, event); err != nil {
			d.logger.Error("projector.failed",
				slog.String("projector", p.Name()),
				slog.String("eventType", event.Type),
				slog.String("eventId", event.ID),
				slog.String("error", err.Error()))
			errs = append(errs, fmt.Errorf("%s: %w", p.Name(), err))
		} else {
			d.logger.Debug("projector.ok",
				slog.String("projector", p.Name()),
				slog.String("eventType", event.Type),
				slog.Duration("duration", time.Since(start)))
		}
	}

	if len(errs) > 0 {
		return fmt.Errorf("%d projector(s) failed: %v", len(errs), errs[0])
	}
	return nil
}

// DispatchBatch processes a batch of events.
func (d *Dispatcher) DispatchBatch(ctx context.Context, events []eventstore.StoredEvent) error {
	for _, event := range events {
		if err := d.Dispatch(ctx, event); err != nil {
			return err
		}
	}
	return nil
}

// ListProjectors returns the names of all registered projectors.
func (d *Dispatcher) ListProjectors() []string {
	d.mu.RLock()
	defer d.mu.RUnlock()

	seen := make(map[string]bool)
	var names []string
	for _, ps := range d.projectors {
		for _, p := range ps {
			if !seen[p.Name()] {
				seen[p.Name()] = true
				names = append(names, p.Name())
			}
		}
	}
	return names
}
