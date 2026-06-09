package es

import (
	"context"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
)

// Writer abstracts ES write transport (bulk upsert/delete). The production
// writer is an HTTP _bulk client; tests use an in-memory fake.
type Writer interface {
	Upsert(ctx context.Context, index, id string, doc map[string]any) error
	Delete(ctx context.Context, index, id string) error
}

// ChangeOp is the kind of change-stream mutation.
type ChangeOp string

const (
	OpUpsert ChangeOp = "upsert"
	OpDelete ChangeOp = "delete"
)

// ChangeEvent is the normalized mutation consumed from a Mongo change stream
// (via runtime/projector) and applied to the ES index.
type ChangeEvent struct {
	Op  ChangeOp
	Doc rtsearch.Document
}

// Indexer applies change events to the unified ES index. It is idempotent:
// upsert uses a stable doc id so replays converge.
type Indexer struct {
	writer Writer
	index  string
}

// NewIndexer constructs an indexer; index defaults to DefaultIndex.
func NewIndexer(writer Writer, index string) *Indexer {
	if index == "" {
		index = DefaultIndex
	}
	return &Indexer{writer: writer, index: index}
}

// IndexID is the stable ES document id for an object.
func IndexID(doc rtsearch.Document) string {
	return doc.ObjectType + ":" + doc.ObjectID
}

// Apply maps and applies a single change event.
func (ix *Indexer) Apply(ctx context.Context, ev ChangeEvent) error {
	id := IndexID(ev.Doc)
	if ev.Op == OpDelete {
		return ix.writer.Delete(ctx, ix.index, id)
	}
	return ix.writer.Upsert(ctx, ix.index, id, DocumentToIndex(ev.Doc))
}

// DocumentToIndex projects a runtime/search Document into the unified ES index
// document, including the AI target and reverse-lookup anchor fields.
func DocumentToIndex(doc rtsearch.Document) map[string]any {
	out := map[string]any{
		"target":     string(rtsearch.TargetForDocument(doc)),
		"objectType": doc.ObjectType,
		"objectId":   doc.ObjectID,
		"title":      doc.Title,
		"summary":    doc.Summary,
		"body":       doc.Body,
		"tags":       doc.Tags,
		"entities":   doc.Entities,
		"visibility": firstNonEmpty(doc.Visibility, "public"),
		"quality":    doc.Popularity,
	}
	if !doc.Freshness.IsZero() {
		out["updatedAt"] = doc.Freshness.UTC().Format("2006-01-02T15:04:05Z07:00")
	}
	// Reverse-lookup anchor fields enable ids/names resolution without type.
	for _, key := range []string{
		"authorId", "authorName", "authorDisplayName",
		"groupId", "groupName", "entityId", "entityName", "conversationId",
	} {
		if v := strings.TrimSpace(doc.Fields[key]); v != "" {
			out[key] = v
		}
	}
	return out
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if s := strings.TrimSpace(v); s != "" {
			return s
		}
	}
	return ""
}
