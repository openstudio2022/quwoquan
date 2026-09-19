package application

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	messaging "quwoquan_service/runtime/messaging"
	rt "quwoquan_service/runtime/search"
	deleted "quwoquan_service/services/search-service/generated/search/search_index_view/events/content_post_PostDeleted"
	privacy "quwoquan_service/services/search-service/generated/search/search_index_view/events/content_post_PostPrivacyRedacted"
	post "quwoquan_service/services/search-service/generated/search/search_index_view/events/content_post_PostPublished"
	purge "quwoquan_service/services/search-service/generated/search/search_index_view/events/content_post_PostPurged"
	"reflect"
	"strconv"
	"strings"
	"time"
)

var ErrContentPostConflict = errors.New("Content Post projection identity/digest conflict")

type ContentPostChange struct {
	EventDigest, PayloadDigest, ObjectDigest, ProjectionDigest string
	SourceVersion                                              int64
	Deleted, Terminal                                          bool
	Document                                                   rt.Document
}
type ContentPostProjection interface {
	ApplyContentPost(context.Context, ContentPostChange) error
}
type ContentPostHandler struct {
	projection ContentPostProjection
	fence      ContentPostDeliveryHandler
}

func (h *ContentPostHandler) BindFenceReconciler(fence ContentPostDeliveryHandler) error {
	if fence == nil || h.fence != nil {
		return errors.New("fence reconciler missing or already bound")
	}
	h.fence = fence
	return nil
}

func NewContentPostHandler(projection ContentPostProjection) (*ContentPostHandler, error) {
	if projection == nil {
		return nil, errors.New("Content Post projection required")
	}
	return &ContentPostHandler{projection: projection}, nil
}
func (h *ContentPostHandler) ApplyContentPostDelivery(ctx context.Context, delivery messaging.StreamDelivery) error {
	for _, field := range delivery.Fields {
		if field.Name == "eventType" && field.Value == "ContentReleaseFenceChanged" {
			if h.fence == nil {
				return errors.New("Content fence reconciler unavailable")
			}
			return h.fence.ApplyContentPostDelivery(ctx, delivery)
		}
	}
	change, err := DecodeContentPostDelivery(delivery)
	if err != nil {
		return err
	}
	return h.projection.ApplyContentPost(ctx, change)
}
func postDigest(v any) string {
	raw, _ := json.Marshal(v)
	sum := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(sum[:])
}

// 使用生成类型的字段/tag递归检查必填，指针只表达null；来源presence单独强制。
func validatePostWire(raw json.RawMessage, t reflect.Type) error {
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		if t.Kind() == reflect.Pointer {
			return nil
		}
		return errors.New("required Content field is null")
	}
	if t.Kind() == reflect.Pointer {
		return validatePostWire(raw, t.Elem())
	}
	if t == reflect.TypeOf(time.Time{}) {
		return nil
	}
	switch t.Kind() {
	case reflect.Struct:
		var obj map[string]json.RawMessage
		if err := json.Unmarshal(raw, &obj); err != nil {
			return err
		}
		for i := 0; i < t.NumField(); i++ {
			field := t.Field(i)
			name := strings.Split(field.Tag.Get("json"), ",")[0]
			value, ok := obj[name]
			if !ok {
				if field.Type.Kind() != reflect.Pointer {
					return fmt.Errorf("required Content field missing: %s", name)
				}
				continue
			}
			if err := validatePostWire(value, field.Type); err != nil {
				return err
			}
		}
	case reflect.Slice:
		var items []json.RawMessage
		if err := json.Unmarshal(raw, &items); err != nil {
			return err
		}
		for _, item := range items {
			if err := validatePostWire(item, t.Elem()); err != nil {
				return err
			}
		}
	}
	return nil
}
func strictPostPayload(raw []byte, value any) error {
	if err := validatePostWire(raw, reflect.TypeOf(value).Elem()); err != nil {
		return err
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(value); err != nil {
		return errors.New("invalid Content generated payload")
	}
	if err := dec.Decode(&struct{}{}); err != io.EOF {
		return errors.New("Content payload trailing JSON")
	}
	return nil
}
func DecodeContentPostDelivery(delivery messaging.StreamDelivery) (ContentPostChange, error) {
	var change ContentPostChange
	if delivery.Stream != "events.content.post_lifecycle" || delivery.ID == "" {
		return change, errors.New("invalid Content stream delivery")
	}
	fields := map[string]string{}
	for _, f := range delivery.Fields {
		if _, ok := fields[f.Name]; ok {
			return change, errors.New("duplicate Content envelope field")
		}
		fields[f.Name] = f.Value
	}
	if fields["eventId"] == "" || fields["aggregateId"] == "" || fields["aggregateType"] != "Post" {
		return change, errors.New("invalid Content envelope identity")
	}
	version, err := strconv.ParseInt(fields["aggregateVersion"], 10, 64)
	if err != nil || version <= 0 {
		return change, errors.New("invalid Content source version")
	}
	occurred, err := time.Parse(time.RFC3339Nano, fields["occurredAt"])
	if err != nil || occurred.IsZero() {
		return change, errors.New("invalid Content occurrence time")
	}
	raw := []byte(fields["payload"])
	var presence map[string]json.RawMessage
	if err = json.Unmarshal(raw, &presence); err != nil {
		return change, err
	}
	for _, key := range []string{"environment", "sourceOwner", "releaseId", "manifestDigest", "releaseDigest"} {
		v, ok := presence[key]
		if !ok || !bytes.Equal(bytes.TrimSpace(v), []byte("null")) {
			return change, errors.New("Data or missing Content source requires separate authoritative reconciliation")
		}
	}
	var safetyRevision int64
	if err = json.Unmarshal(presence["safetyRevision"], &safetyRevision); err != nil || safetyRevision < 1 {
		return change, errors.New("Content safety revision missing or invalid")
	}
	var sourceVersion int64
	if err = json.Unmarshal(presence["sourceVersion"], &sourceVersion); err != nil || sourceVersion != version {
		return change, errors.New("Content source/envelope version mismatch")
	}
	var id string
	var doc rt.Document
	isDeleted, terminal := false, false
	switch fields["eventType"] {
	case "PostPublished", "PostUpdated", "PostSettingsUpdated", "PostModerationRejected":
		var p post.PostLifecycleProjectionPayload
		if err = strictPostPayload(raw, &p); err != nil {
			return change, err
		}
		if _, ok := presence["publishedAt"]; !ok {
			return change, errors.New("publishedAt presence required")
		}
		if _, ok := presence["visitedAt"]; !ok {
			return change, errors.New("visitedAt presence required")
		}
		if p.CreatedAt.IsZero() || p.UpdatedAt.IsZero() || p.AuthorId == "" || p.Status == "" || p.Visibility == "" || p.ModerationStatus == "" {
			return change, errors.New("incomplete Content public state")
		}
		if p.Status == "published" && (p.PublishedAt == nil || p.PublishedAt.IsZero()) {
			return change, errors.New("published Post requires actual publication time")
		}
		id = p.PostId
		isDeleted = p.Status != "published" || p.Visibility != "public" || p.ModerationStatus != "approved"
		terminal = p.Status == "deleted"
		doc = ContentPostDocument(p)
	case "PostDeleted":
		var p deleted.PostDeletedPayload
		if err = strictPostPayload(raw, &p); err != nil {
			return change, err
		}
		if p.DeletedAt.IsZero() {
			return change, errors.New("deletion time required")
		}
		id = p.PostId
		isDeleted = true
		terminal = true
	case "PostPrivacyRedacted":
		var p privacy.PostPrivacyRedactedPayload
		if err = strictPostPayload(raw, &p); err != nil {
			return change, err
		}
		if p.RedactedAt.IsZero() || p.RetentionExpiresAt.IsZero() {
			return change, errors.New("redaction time required")
		}
		id = p.PostId
		isDeleted = true
		terminal = true
	case "PostPurged":
		var p purge.PostPurgedPayload
		if err = strictPostPayload(raw, &p); err != nil {
			return change, err
		}
		if p.PurgedAt.IsZero() {
			return change, errors.New("purge time required")
		}
		id = p.PostId
		isDeleted = true
		terminal = true
	default:
		return change, errors.New("unsupported Content event including unimplemented fence")
	}
	if id == "" || id != fields["aggregateId"] {
		return change, errors.New("Content object identity mismatch")
	}
	if isDeleted {
		doc = rt.Document{ObjectType: "content.post", ObjectID: id}
	}
	var canonical any
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err = dec.Decode(&canonical); err != nil {
		return change, err
	}
	return ContentPostChange{EventDigest: postDigest(fields["eventId"]), PayloadDigest: postDigest([]any{fields["eventType"], id, version, occurred.UTC(), canonical}), ObjectDigest: postDigest([]string{"ordinary", "content.post", id}), ProjectionDigest: postDigest([]any{doc, isDeleted, terminal}), SourceVersion: version, Deleted: isDeleted, Terminal: terminal, Document: doc}, nil
}
func text(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}

func enumText[T ~string](p *T) string {
	if p == nil {
		return ""
	}
	return string(*p)
}
func count(p *int64) int64 {
	if p == nil {
		return 0
	}
	return *p
}

// Content公开事件是唯一字段源；Provider投影保留现役卡片/媒体绑定，不回源读取。
func ContentPostDocument(p post.PostLifecycleProjectionPayload) rt.Document {
	tags := []string{}
	if p.TagRefs != nil {
		tags = *p.TagRefs
	}
	entities := []string{}
	if p.EntityRefs != nil {
		entities = *p.EntityRefs
	}
	d := rt.Document{ObjectType: "content.post", ObjectID: p.PostId, Title: p.Title, Body: p.Body, Summary: p.Summary, SourceDomain: "content", ContentType: string(p.ContentType), Visibility: p.Visibility, BadgeLabel: "内容", Tags: tags, Entities: entities, Popularity: float64(count(p.LikeCount) + count(p.CommentCount) + count(p.ShareCount)), Fields: map[string]string{"authorId": p.AuthorId, "authorName": p.AuthorDisplayNameSnapshot, "authorDisplayName": p.AuthorDisplayNameSnapshot, "authorAvatarUrl": p.AuthorAvatarUrlSnapshot, "coverUrl": p.CoverUrl, "coverWidth": strconv.FormatInt(p.Width, 10), "coverHeight": strconv.FormatInt(p.Height, 10), "likeCount": strconv.FormatInt(count(p.LikeCount), 10)}}
	if d.Summary == "" {
		d.Summary = p.Body
	}
	if p.PublishedAt != nil {
		d.Freshness = *p.PublishedAt
		d.Fields["publishedAt"] = p.PublishedAt.UTC().Format(time.RFC3339Nano)
	}
	if p.MediaItems != nil {
		for _, m := range *p.MediaItems {
			if text(m.CoverUrl) == p.CoverUrl && p.CoverUrl != "" {
				id := text(m.CoverAssetId)
				if id == "" {
					id = text(m.MediaAssetId)
				}
				d.Fields["coverAssetId"] = id
				d.Fields["coverAccessMode"] = enumText(m.AccessMode)
				break
			}
			if m.Url == p.CoverUrl && p.CoverUrl != "" {
				d.Fields["coverAssetId"] = text(m.MediaAssetId)
				d.Fields["coverAccessMode"] = enumText(m.AccessMode)
			}
		}
	}
	return d
}
