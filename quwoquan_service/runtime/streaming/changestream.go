package streaming

import (
	"context"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// ChangeEvent represents a MongoDB Change Stream event.
type ChangeEvent struct {
	OperationType string         `bson:"operationType" json:"operationType"`
	DocumentKey   bson.M         `bson:"documentKey"   json:"documentKey"`
	FullDocument  bson.M         `bson:"fullDocument"  json:"fullDocument,omitempty"`
	UpdateDesc    *UpdateDesc    `bson:"updateDescription" json:"updateDescription,omitempty"`
	ClusterTime   time.Time      `bson:"clusterTime"   json:"clusterTime"`
	Namespace     ChangeNS       `bson:"ns"            json:"ns"`
}

type UpdateDesc struct {
	UpdatedFields bson.M   `bson:"updatedFields" json:"updatedFields,omitempty"`
	RemovedFields []string `bson:"removedFields"  json:"removedFields,omitempty"`
}

type ChangeNS struct {
	DB   string `bson:"db"   json:"db"`
	Coll string `bson:"coll" json:"coll"`
}

// ChangeHandler processes a change event. Return error to trigger retry.
type ChangeHandler func(ctx context.Context, event ChangeEvent) error

// ChangeStreamWatcher watches a MongoDB collection and dispatches changes.
type ChangeStreamWatcher struct {
	coll     *mongo.Collection
	pipeline mongo.Pipeline
	handler  ChangeHandler
	logger   *slog.Logger
	opts     *changeStreamOpts
}

type changeStreamOpts struct {
	fullDocument string
	batchSize    int32
}

type WatcherOption func(*changeStreamOpts)

// WithFullDocument enables returning the full document on change events.
func WithFullDocument() WatcherOption {
	return func(o *changeStreamOpts) { o.fullDocument = "updateLookup" }
}

func WithBatchSize(n int32) WatcherOption {
	return func(o *changeStreamOpts) { o.batchSize = n }
}

// NewChangeStreamWatcher creates a watcher for a collection.
func NewChangeStreamWatcher(
	coll *mongo.Collection,
	pipeline mongo.Pipeline,
	handler ChangeHandler,
	logger *slog.Logger,
	opts ...WatcherOption,
) *ChangeStreamWatcher {
	o := &changeStreamOpts{batchSize: 100}
	for _, fn := range opts {
		fn(o)
	}
	return &ChangeStreamWatcher{
		coll:     coll,
		pipeline: pipeline,
		handler:  handler,
		logger:   logger,
		opts:     o,
	}
}

// Watch starts watching. Blocks until context is cancelled.
// Automatically resumes on transient errors.
func (w *ChangeStreamWatcher) Watch(ctx context.Context) error {
	for {
		if err := w.watchOnce(ctx); err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			w.logger.Warn("changestream.reconnecting",
				slog.String("collection", w.coll.Name()),
				slog.String("error", err.Error()))
			time.Sleep(2 * time.Second)
			continue
		}
		return nil
	}
}

func (w *ChangeStreamWatcher) watchOnce(ctx context.Context) error {
	csOpts := options.ChangeStream().SetBatchSize(w.opts.batchSize)
	if w.opts.fullDocument != "" {
		csOpts.SetFullDocument(options.FullDocument(w.opts.fullDocument))
	}

	cs, err := w.coll.Watch(ctx, w.pipeline, csOpts)
	if err != nil {
		return err
	}
	defer cs.Close(ctx)

	w.logger.Info("changestream.started", slog.String("collection", w.coll.Name()))

	for cs.Next(ctx) {
		var event ChangeEvent
		if err := cs.Decode(&event); err != nil {
			w.logger.Error("changestream.decode", slog.String("error", err.Error()))
			continue
		}

		if err := w.handler(ctx, event); err != nil {
			w.logger.Error("changestream.handler",
				slog.String("operation", event.OperationType),
				slog.String("error", err.Error()))
		}
	}

	return cs.Err()
}
