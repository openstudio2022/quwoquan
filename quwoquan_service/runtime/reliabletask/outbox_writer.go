package reliabletask

import "context"

// TaskOutboxWriter is the only runtime entry point business services should use
// to declare reliable asynchronous work inside the current business transaction.
type TaskOutboxWriter struct {
	Store Store
}

func NewTaskOutboxWriter(store Store) TaskOutboxWriter {
	return TaskOutboxWriter{Store: store}
}

func (w TaskOutboxWriter) AddTask(ctx context.Context, req DeclareTaskRequest) (TaskOutboxRecord, error) {
	if w.Store == nil {
		return TaskOutboxRecord{}, ErrStoreRequired
	}
	var record TaskOutboxRecord
	err := w.Store.RunInTransaction(ctx, func(txCtx context.Context) error {
		created, err := w.Store.DeclareTask(txCtx, req)
		if err != nil {
			return err
		}
		record = created
		return nil
	})
	return record, err
}
