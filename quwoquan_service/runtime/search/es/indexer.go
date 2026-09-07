package es

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
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

// VersionedWriter 是唯一的 Elasticsearch 写传输契约：所有投影写入都必须携带
// 权威对象的 sourceVersion，由 Elasticsearch 在分片内原子比较；删除以带版本的
// tombstone 文档落盘而不是物理 DELETE（search-provider-routing DEC-002）。
// 实现不得用 read-before-write 模拟该契约；无版本的 Upsert/Delete 写入面已删除。
type VersionedWriter interface {
	UpsertVersioned(
		ctx context.Context,
		index string,
		id string,
		sourceVersion int64,
		doc map[string]any,
	) (bool, error)
	TombstoneVersioned(
		ctx context.Context,
		index string,
		id string,
		objectType string,
		objectID string,
		sourceVersion int64,
	) (bool, error)
}

// ChangeOp is the kind of projection mutation.
type ChangeOp string

const (
	OpUpsert ChangeOp = "upsert"
	OpDelete ChangeOp = "delete"
)

// VersionedChangeEvent is an explicitly source-versioned projection mutation.
// SourceVersion 必须来自权威对象自身的单调版本字段；调用方不得凭空捏造。
type VersionedChangeEvent struct {
	Op            ChangeOp
	Doc           rtsearch.Document
	SourceVersion int64
}

// Indexer applies versioned change events to the unified ES index. It is
// idempotent: upsert uses a stable doc id so replays converge, and the
// provider-side version fence rejects stale or out-of-order writes.
type Indexer struct {
	writer VersionedWriter
	index  string
}

// NewIndexer constructs an indexer; index defaults to DefaultIndex.
func NewIndexer(writer VersionedWriter, index string) *Indexer {
	if index == "" {
		index = DefaultIndex
	}
	return &Indexer{writer: writer, index: index}
}

// IndexID is the stable ES document id for an object.
func IndexID(doc rtsearch.Document) string {
	return doc.ObjectType + ":" + doc.ObjectID
}

// ApplyVersioned validates and applies one projection mutation using the
// provider's atomic source-version comparison. False/nil means only a stale
// write or same-version/same-digest replay; divergent equal versions error.
func (ix *Indexer) ApplyVersioned(ctx context.Context, ev VersionedChangeEvent) (bool, error) {
	if ix == nil || ix.writer == nil {
		return false, errors.New("es: versioned indexer is unavailable")
	}
	if ev.SourceVersion <= 0 {
		return false, errors.New("es: sourceVersion must be positive")
	}
	if strings.TrimSpace(ev.Doc.ObjectType) == "" || strings.TrimSpace(ev.Doc.ObjectID) == "" {
		return false, errors.New("es: versioned document identity is required")
	}
	writer := ix.writer
	id := IndexID(ev.Doc)
	switch ev.Op {
	case OpUpsert:
		return writer.UpsertVersioned(
			ctx,
			ix.index,
			id,
			ev.SourceVersion,
			DocumentToIndex(ev.Doc, ev.SourceVersion),
		)
	case OpDelete:
		return writer.TombstoneVersioned(
			ctx,
			ix.index,
			id,
			ev.Doc.ObjectType,
			ev.Doc.ObjectID,
			ev.SourceVersion,
		)
	default:
		return false, fmt.Errorf("es: unsupported versioned change operation %q", ev.Op)
	}
}

// WithCanonicalSourceDigest clones a versioned Elasticsearch source and binds
// it to a deterministic SHA-256 over every canonical fact except the digest
// field itself. encoding/json sorts map keys, yielding stable bytes for replay.
func WithCanonicalSourceDigest(doc map[string]any) (map[string]any, error) {
	canonical := make(map[string]any, len(doc))
	for key, value := range doc {
		if key != "sourceDigest" {
			canonical[key] = value
		}
	}
	payload, err := json.Marshal(canonical)
	if err != nil {
		return nil, fmt.Errorf("es: canonicalize versioned source: %w", err)
	}
	digest := sha256.Sum256(payload)
	canonical["sourceDigest"] = fmt.Sprintf("sha256:%x", digest)
	return canonical, nil
}

// VersionedTombstoneDocument is the canonical soft-delete source shared by
// production and contract writers.
func VersionedTombstoneDocument(
	objectType string,
	objectID string,
	sourceVersion int64,
) (map[string]any, error) {
	if strings.TrimSpace(objectType) == "" || strings.TrimSpace(objectID) == "" {
		return nil, errors.New("es: tombstone identity is required")
	}
	return WithCanonicalSourceDigest(map[string]any{
		"objectType":    strings.TrimSpace(objectType),
		"objectId":      strings.TrimSpace(objectID),
		"sourceVersion": sourceVersion,
		"deleted":       true,
	})
}

// DocumentToIndex projects a runtime/search Document into the unified ES index
// document, including the AI target and reverse-lookup anchor fields.
func DocumentToIndex(doc rtsearch.Document, sourceVersion ...int64) map[string]any {
	out := map[string]any{
		"deleted":    false,
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
	if len(sourceVersion) > 0 && sourceVersion[0] > 0 {
		out["sourceVersion"] = sourceVersion[0]
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
		// The ES query embeds the full commercial ranking (function_score covers
		// freshness/quality/geo on top of text relevance), so the engine order is
		// final; the shared ranker must not derive a second score.
		ServerRanked: true,
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
