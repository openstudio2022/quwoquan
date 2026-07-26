package runtimeobservability

import (
	"bytes"
	"encoding/json"
	"io"
	"strings"
	"sync"
	"time"
)

// RuntimeLogFieldBatchExporter receives already canonical, flattened records.
// Implementations normally batch it to the configured runtime logstore.
type RuntimeLogFieldBatchExporter func([]map[string]string)

// RuntimeLogExportWriter mirrors canonical service stdout to an asynchronous
// exporter. Logging must never block request handling or cause a feedback loop
// when the remote logstore is unavailable, so malformed records and a full
// export queue are deliberately dropped after stdout has been written.
type RuntimeLogExportWriter struct {
	primary io.Writer
	export  RuntimeLogFieldBatchExporter
	queue   chan map[string]string
	stop    chan struct{}
	done    chan struct{}
	once    sync.Once
}

func NewRuntimeLogExportWriter(primary io.Writer, queueSize int, export RuntimeLogFieldBatchExporter) *RuntimeLogExportWriter {
	if primary == nil {
		primary = io.Discard
	}
	if queueSize < 1 {
		queueSize = 1
	}
	writer := &RuntimeLogExportWriter{
		primary: primary,
		export:  export,
		queue:   make(chan map[string]string, queueSize),
		stop:    make(chan struct{}),
		done:    make(chan struct{}),
	}
	go writer.run()
	return writer
}

func (w *RuntimeLogExportWriter) Write(input []byte) (int, error) {
	written, err := w.primary.Write(input)
	for _, raw := range bytes.Split(input, []byte("\n")) {
		line := strings.TrimSpace(string(raw))
		if line == "" {
			continue
		}
		var payload map[string]any
		if json.Unmarshal([]byte(line), &payload) != nil {
			continue
		}
		fields, parseErr := CanonicalRuntimeLogFields(payload)
		if parseErr != nil {
			continue
		}
		select {
		case w.queue <- fields:
		default:
			// A full queue must not block a service request; primary stdout
			// remains the durable collector fallback.
		}
	}
	return written, err
}

func (w *RuntimeLogExportWriter) Close() {
	w.once.Do(func() {
		close(w.stop)
		<-w.done
	})
}

func (w *RuntimeLogExportWriter) run() {
	defer close(w.done)
	const maxBatchItems = 50
	flushEvery := time.NewTimer(250 * time.Millisecond)
	defer flushEvery.Stop()
	batch := make([]map[string]string, 0, maxBatchItems)
	flush := func() {
		if len(batch) == 0 {
			return
		}
		if w.export != nil {
			w.export(batch)
		}
		batch = make([]map[string]string, 0, maxBatchItems)
	}
	for {
		select {
		case fields := <-w.queue:
			batch = append(batch, fields)
			if len(batch) >= maxBatchItems {
				flush()
			}
		case <-flushEvery.C:
			flush()
			flushEvery.Reset(250 * time.Millisecond)
		case <-w.stop:
			for {
				select {
				case fields := <-w.queue:
					batch = append(batch, fields)
				default:
					flush()
					return
				}
			}
		}
	}
}
