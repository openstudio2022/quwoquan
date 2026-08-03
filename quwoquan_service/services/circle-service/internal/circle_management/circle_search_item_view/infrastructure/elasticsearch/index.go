package elasticsearch

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	viewapp "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/application"
)

type Index struct{ indexer *es.Indexer }

func NewIndex(indexer *es.Indexer) *Index {
	if indexer == nil {
		panic("CircleSearchItemView Elasticsearch indexer is required")
	}
	return &Index{indexer: indexer}
}

func (index *Index) UpsertIfNewer(ctx context.Context, item viewapp.SearchItem) (bool, error) {
	document, err := documentFrom(item)
	if err != nil {
		return false, err
	}
	if err := index.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: document}); err != nil {
		return false, err
	}
	return true, nil
}

func (index *Index) DeleteIfNotOlder(ctx context.Context, circleID string, sourceVersion int64) (bool, error) {
	if strings.TrimSpace(circleID) == "" || sourceVersion <= 0 {
		return false, fmt.Errorf("CircleSearchItemView delete requires identity and sourceVersion")
	}
	if err := index.indexer.Apply(ctx, es.ChangeEvent{
		Op:  es.OpDelete,
		Doc: rtsearch.Document{ObjectType: rtsearch.ObjectTypeCircle, ObjectID: strings.TrimSpace(circleID)},
	}); err != nil {
		return false, err
	}
	return true, nil
}

func documentFrom(item viewapp.SearchItem) (rtsearch.Document, error) {
	if strings.TrimSpace(item.CircleID) == "" || strings.TrimSpace(item.DisplayName) == "" || item.SourceVersion <= 0 {
		return rtsearch.Document{}, fmt.Errorf("CircleSearchItemView item is invalid")
	}
	categoryID := strings.TrimSpace(item.CategoryID)
	if categoryID == "" {
		categoryID = strings.TrimSpace(item.DomainID)
	}
	if categoryID == "" {
		categoryID = "all"
	}
	return rtsearch.Document{
		ObjectType: rtsearch.ObjectTypeCircle, ObjectID: strings.TrimSpace(item.CircleID),
		Title: strings.TrimSpace(item.DisplayName), Summary: strings.TrimSpace(item.Description),
		SourceDomain: "circle", ContentType: strings.TrimSpace(item.Kind),
		Visibility: strings.TrimSpace(item.Visibility), BadgeLabel: "圈子",
		Tags:       append([]string(nil), item.Tags...),
		Popularity: float64(item.MemberCount + item.PostCount), Freshness: item.UpdatedAt.UTC(),
		Fields: map[string]string{
			"circleId": item.CircleID, "circleName": item.DisplayName,
			"coverUrl": item.CoverURL, "categoryId": categoryID,
			"subCategory": item.SubCategory, "domainId": item.DomainID,
			"kind": item.Kind, "displaySubjectType": item.DisplaySubjectType,
			"memberCount":         strconv.FormatInt(item.MemberCount, 10),
			"postCount":           strconv.FormatInt(item.PostCount, 10),
			"linkedHomepageId":    item.LinkedHomepageID,
			"linkedHomepageType":  item.LinkedHomepageType,
			"linkedHomepageTitle": item.LinkedHomepageTitle,
			"sourceVersion":       strconv.FormatInt(item.SourceVersion, 10),
		},
	}, nil
}

var _ viewapp.Index = (*Index)(nil)
var _ = time.Time{}
