package es

import (
	"context"
	"strings"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

// anchorFieldKeys are the reverse-lookup fields flattened into the index doc so
// ids/names can resolve objects without their type. Shared by projection and
// reconstruction so the round trip stays lossless.
var anchorFieldKeys = []string{
	"authorId", "authorName", "authorDisplayName",
	"groupId", "groupName", "entityId", "entityName", "conversationId",
	// Cross-object place reference (R-S05e). placeId/placeName ride the same
	// Fields-flattening path so the location dimension round-trips losslessly.
	"placeId", "placeName",
}

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
	// contentType keeps article/photo/video distinguishable on read-back so the
	// shared ranker can re-derive the AI target without guessing.
	if ct := strings.TrimSpace(doc.ContentType); ct != "" {
		out["contentType"] = ct
	}
	if !doc.Freshness.IsZero() {
		out["updatedAt"] = doc.Freshness.UTC().Format("2006-01-02T15:04:05Z07:00")
	}
	// Location dimension: project Geo to the ES geo_point object shape ({lat,lon})
	// so geo_distance recall works. Written only when the object has real coords.
	if doc.Geo != nil {
		out["geo"] = map[string]any{"lat": doc.Geo.Lat, "lon": doc.Geo.Lng}
	}
	// Payload is a presentation-only slice retained in _source with indexing
	// disabled by the mapping. This keeps every object self-contained on the
	// result path without creating dynamic ES fields or synchronous source-service
	// backfill calls.
	if len(doc.Fields) > 0 {
		payload := make(map[string]any, len(doc.Fields))
		for key, value := range doc.Fields {
			if strings.TrimSpace(key) == "" {
				continue
			}
			payload[key] = value
		}
		if len(payload) > 0 {
			out["payload"] = payload
		}
	}
	// Reverse-lookup anchor fields enable ids/names resolution without type.
	for _, key := range anchorFieldKeys {
		if v := strings.TrimSpace(doc.Fields[key]); v != "" {
			out[key] = v
		}
	}
	return out
}

// IndexToDocument reconstructs a runtime/search Document from an ES _source. It
// is the inverse of DocumentToIndex (lossless for the indexed fields) so the ES
// backend can feed the shared CrossTypeRanker the same shape native sources do.
func IndexToDocument(src map[string]any) rtsearch.Document {
	doc := rtsearch.Document{
		ObjectType:  asString(src["objectType"]),
		ObjectID:    asString(src["objectId"]),
		Title:       asString(src["title"]),
		Summary:     asString(src["summary"]),
		Body:        asString(src["body"]),
		ContentType: asString(src["contentType"]),
		Visibility:  asString(src["visibility"]),
		Tags:        asStringSlice(src["tags"]),
		Entities:    asStringSlice(src["entities"]),
		Popularity:  asFloat(src["quality"]),
	}
	if ts := asString(src["updatedAt"]); ts != "" {
		if t, err := time.Parse(time.RFC3339, ts); err == nil {
			doc.Freshness = t
		}
	}
	// Reconstruct the geo dimension from the stored geo_point ({lat,lon}). The
	// presence of the "geo" key (written only for real coords) keeps the round
	// trip lossless even for valid (0,0) edge coordinates.
	if g, ok := src["geo"].(map[string]any); ok {
		doc.Geo = &rtsearch.GeoPoint{Lat: asFloat(g["lat"]), Lng: asFloat(g["lon"])}
	}
	fields := payloadFields(src["payload"])
	for _, key := range anchorFieldKeys {
		if v := asString(src[key]); v != "" {
			fields[key] = v
		}
	}
	if len(fields) > 0 {
		doc.Fields = fields
	}
	return doc
}

func payloadFields(value any) map[string]string {
	fields := map[string]string{}
	switch payload := value.(type) {
	case map[string]any:
		for key, raw := range payload {
			if text, ok := raw.(string); ok {
				fields[key] = text
			}
		}
	case map[string]string:
		for key, text := range payload {
			fields[key] = text
		}
	}
	return fields
}

// IndexToCandidate wraps a reconstructed Document with the ES relevance score so
// the shared ranker can fuse it with its own freshness/popularity boosts.
func IndexToCandidate(src map[string]any, score float64) rtsearch.RecallCandidate {
	return rtsearch.RecallCandidate{
		Document:  IndexToDocument(src),
		BaseScore: score,
		Source:    "elasticsearch",
	}
}

func asString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func asFloat(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case float32:
		return float64(n)
	case int:
		return float64(n)
	case int64:
		return float64(n)
	default:
		return 0
	}
}

func asStringSlice(v any) []string {
	switch arr := v.(type) {
	case []string:
		return arr
	case []any:
		out := make([]string, 0, len(arr))
		for _, e := range arr {
			if s := asString(e); s != "" {
				out = append(out, s)
			}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	default:
		return nil
	}
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if s := strings.TrimSpace(v); s != "" {
			return s
		}
	}
	return ""
}
