package es

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	rt "quwoquan_service/runtime/search"
	"sort"
)

// SchemaGeneration来自实际生成mapping的canonical摘要，不是兼容版本选择器。
func (c *Client) SchemaGeneration() string {
	d, _ := rt.CreatorCanonicalDigest(BuildCreateIndexBody(c.cfg.Schema), "")
	return d
}
func WithReleaseBinding(ctx context.Context, b *rt.ReleaseQueryPreparationBinding) context.Context {
	return rt.WithCreatorQueryBinding(ctx, b)
}
func ReleaseBindingFilter(b rt.ReleaseQueryPreparationBinding) map[string]any {
	return map[string]any{"bool": map[string]any{"filter": []any{map[string]any{"term": map[string]any{"sourceKind": "release_candidate"}}, map[string]any{"term": map[string]any{"releaseBindingId": b.ID()}}}}}
}
func CreatorVisibilityFilter(b *rt.ReleaseQueryPreparationBinding) map[string]any {
	ordinary := ordinarySourceQuery()
	if b == nil {
		return ordinary
	}
	data := []any{map[string]any{"term": map[string]any{"sourceKind": "release_candidate"}}, map[string]any{"term": map[string]any{"releaseSliceBinding.release.environment": b.Release.Environment}}, map[string]any{"term": map[string]any{"releaseSliceBinding.release.sourceOwner": b.Release.SourceOwner}}, map[string]any{"term": map[string]any{"releaseSliceBinding.release.releaseId": b.Release.ReleaseID}}, map[string]any{"term": map[string]any{"releaseSliceBinding.release.manifestDigest": b.Release.ManifestDigest}}, map[string]any{"term": map[string]any{"releaseSliceBinding.providerBindingGeneration": b.ProviderBindingGeneration}}, map[string]any{"term": map[string]any{"releaseSliceBinding.schemaGeneration": b.SchemaGeneration}}}
	for field, value := range map[string]string{
		"releaseSourceIdentity.release.environment":    b.Release.Environment,
		"releaseSourceIdentity.release.sourceOwner":    b.Release.SourceOwner,
		"releaseSourceIdentity.release.releaseId":      b.Release.ReleaseID,
		"releaseSourceIdentity.release.manifestDigest": b.Release.ManifestDigest,
	} {
		data = append(data, map[string]any{"term": map[string]any{field: value}})
	}
	return map[string]any{"bool": map[string]any{"minimum_should_match": 1, "should": []any{ordinary, map[string]any{"bool": map[string]any{"filter": data}}}}}
}
func filterCreatorSearch(body map[string]any, b *rt.ReleaseQueryPreparationBinding) {
	query, ok := body["query"]
	if !ok {
		query = map[string]any{"match_all": map[string]any{}}
	}
	body["query"] = map[string]any{"bool": map[string]any{"must": []any{query}, "filter": []any{CreatorVisibilityFilter(b)}}}
	apply := func(knn map[string]any) {
		clauses := []any{CreatorVisibilityFilter(b)}
		if old, exists := knn["filter"]; exists {
			clauses = append(clauses, old)
		}
		knn["filter"] = map[string]any{"bool": map[string]any{"filter": clauses}}
	}
	switch knn := body["knn"].(type) {
	case map[string]any:
		apply(knn)
	case []map[string]any:
		for _, item := range knn {
			apply(item)
		}
	case []any:
		for _, item := range knn {
			if value, ok := item.(map[string]any); ok {
				apply(value)
			}
		}
	}
}
func ReleaseDocumentID(b rt.ReleaseQueryPreparationBinding, i rt.ReleaseCandidateObjectIdentity) string {
	d, _ := rt.CreatorCanonicalDigest(map[string]any{"releaseSliceBinding": b, "objectType": i.ObjectType, "objectId": i.ObjectID}, "")
	return "release-slice:" + d
}
func releaseDocuments(b rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot) (map[string]map[string]any, error) {
	if s.Validate() != nil || s.Release() != b.Release || b.Slice != s.Kind+"_search" {
		return nil, rt.ErrCreatorSourceInvalid
	}
	docs := map[string]map[string]any{}
	ids := s.Identities()
	for n, i := range ids {
		document := rt.Document{ObjectType: i.ObjectType, ObjectID: i.ObjectID, Visibility: "public", Fields: map[string]string{}}
		switch s.Kind {
		case "creator":
			p := s.Creator.Profiles[n]
			document.Title = p.DisplayName
			document.Tags = p.IdentityTags
			if p.Bio != nil {
				document.Summary = *p.Bio
			}
			document.Fields["userHandle"] = p.UserHandle
			document.Fields["deepLink"] = "quwoquan://user/" + p.UserHandle
			document.Fields["authorId"] = p.AuthorID
			document.Fields["authorName"] = p.DisplayName
			if p.AvatarURL != nil {
				document.Fields["avatarUrl"] = *p.AvatarURL
				document.Fields["avatarAssetId"] = *p.AvatarAssetID
				document.Fields["avatarAccessMode"] = *p.AvatarAccessMode
			}
		case "post":
			p := s.Post.Posts[n]
			document.Title = p.Title
			document.Body = p.Body
			document.Summary = p.Summary
			document.ContentType = p.ContentType
			document.Tags = p.TagRefs
			document.Entities = p.EntityRefs
			document.Fields["deepLink"] = p.DeepLink
			document.Fields["authorId"] = p.AuthorID
			document.Fields["authorName"] = p.AuthorDisplayName
		case "homepage":
			p := s.Homepage.Homepages[n]
			document.Title = p.Title
			document.Body = p.IntroductionMarkdown
			document.ContentType = p.HomepageType
			document.Tags = p.TagRefs
			document.Entities = []string{p.CanonicalEntityID}
			document.Fields["deepLink"] = p.DeepLink
			if p.Location != nil {
				document.Geo = &rt.GeoPoint{Lat: p.Location.Latitude, Lng: p.Location.Longitude}
			}
		}
		row := DocumentToIndex(document, i.SourceVersion)
		row["sourceKind"] = "release_candidate"
		row["releaseSliceBinding"] = b
		row["releaseSourceIdentity"] = i
		row["releaseBindingId"] = b.ID()
		d, err := WithCanonicalSourceDigest(row)
		if err != nil {
			return nil, err
		}
		docs[ReleaseDocumentID(b, i)] = d
	}
	return docs, nil
}
func (c *Client) verifyReleaseMapping(ctx context.Context) error {
	physical, err := c.physicalIndexFor(ctx, c.IndexName())
	if err != nil {
		return err
	}
	if physical == "" {
		return ErrIndexSchemaIncompatible
	}
	if err = c.VerifyPhysicalNamespace(ctx, physical); err != nil {
		return err
	}
	status, raw, err := c.send(ctx, http.MethodGet, "/"+c.IndexName()+"/_mapping", nil, "")
	if err != nil {
		return err
	}
	if status != 200 {
		return ErrDependencyUnavailable
	}
	var mappings map[string]struct {
		Mappings map[string]any `json:"mappings"`
	}
	if json.Unmarshal(raw, &mappings) != nil || len(mappings) != 1 {
		return ErrIndexSchemaIncompatible
	}
	expected := BuildCreateIndexBody(c.cfg.Schema)["mappings"].(map[string]any)["properties"].(map[string]any)
	for _, index := range mappings {
		props, ok := index.Mappings["properties"].(map[string]any)
		if !ok {
			return ErrIndexSchemaIncompatible
		}
		for _, key := range []string{"releaseSliceBinding", "releaseSourceIdentity", "releaseBindingId", "sourceKind"} {
			want, _ := rt.CreatorCanonicalDigest(expected[key], "")
			got, _ := rt.CreatorCanonicalDigest(props[key], "")
			if want != got {
				return ErrIndexSchemaIncompatible
			}
		}
	}
	return nil
}

func (c *Client) WriteReleaseCandidate(ctx context.Context, b rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot) ([]string, error) {
	if b.SchemaGeneration != c.SchemaGeneration() {
		return nil, ErrIndexSchemaIncompatible
	}
	docs, err := releaseDocuments(b, s)
	if err != nil {
		return nil, err
	}
	out := []string{}
	for _, i := range s.Identities() {
		id := ReleaseDocumentID(b, i)
		if _, err = c.UpsertVersioned(ctx, c.WriteIndexName(), id, i.SourceVersion, docs[id]); err != nil {
			return out, err
		}
		out = append(out, i.ObjectID)
	}
	return out, nil
}
func (c *Client) VerifyReleaseCandidate(ctx context.Context, b rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot) ([]rt.ReleaseQueryClassEvidence, error) {
	if err := c.verifyReleaseMapping(ctx); err != nil {
		return nil, err
	}
	if b.SchemaGeneration != c.SchemaGeneration() {
		return nil, ErrIndexSchemaIncompatible
	}
	expected, err := releaseDocuments(b, s)
	if err != nil {
		return nil, err
	}
	evidence := []rt.ReleaseQueryClassEvidence{}
	// 原始集合审计只证明count/facet，用户查询语义由下方生产Retrieve管线另验。
	for _, class := range []string{"count", "facet"} {
		body := map[string]any{"size": 1001, "track_total_hits": true, "query": ReleaseBindingFilter(b), "sort": []any{map[string]any{"objectId": "asc"}}}
		if class == "facet" {
			body["aggs"] = map[string]any{"objects": map[string]any{"terms": map[string]any{"field": "objectId", "size": 1001}}}
		}
		EnsureCurrentSearchBody(body)
		status, raw, err := c.send(ctx, http.MethodPost, "/"+c.IndexName()+"/_search", body, "application/json")
		if err != nil {
			return nil, err
		}
		if status != 200 {
			return nil, fmt.Errorf("%w: query status %d", ErrDependencyUnavailable, status)
		}
		var result struct {
			Hits struct {
				Total struct {
					Value int `json:"value"`
				} `json:"total"`
				Hits []struct {
					ID     string          `json:"_id"`
					Source json.RawMessage `json:"_source"`
				} `json:"hits"`
			} `json:"hits"`
			Aggregations struct {
				Objects struct {
					Buckets []struct {
						Key   string `json:"key"`
						Count int    `json:"doc_count"`
					} `json:"buckets"`
				} `json:"objects"`
			} `json:"aggregations"`
		}
		if err = json.Unmarshal(raw, &result); err != nil {
			return nil, err
		}
		if result.Hits.Total.Value != len(expected) || len(result.Hits.Hits) != len(expected) {
			return nil, fmt.Errorf("%w: incomplete candidate query", ErrDependencyUnavailable)
		}
		if class == "facet" {
			if len(result.Aggregations.Objects.Buckets) != len(expected) {
				return nil, ErrSameVersionDigestConflict
			}
			ids := map[string]bool{}
			for _, id := range s.Identities() {
				ids[id.ObjectID] = true
			}
			for _, bucket := range result.Aggregations.Objects.Buckets {
				if !ids[bucket.Key] || bucket.Count != 1 {
					return nil, ErrSameVersionDigestConflict
				}
				delete(ids, bucket.Key)
			}
		}
		rows := []map[string]string{}
		seen := map[string]bool{}
		for _, hit := range result.Hits.Hits {
			want, ok := expected[hit.ID]
			if !ok || seen[hit.ID] {
				return nil, ErrSameVersionDigestConflict
			}
			seen[hit.ID] = true
			var got map[string]any
			decoder := json.NewDecoder(bytes.NewReader(hit.Source))
			decoder.UseNumber()
			if err = decoder.Decode(&got); err != nil {
				return nil, err
			}
			wd, _ := rt.CreatorCanonicalDigest(want, "")
			gd, _ := rt.CreatorCanonicalDigest(got, "")
			if wd != gd {
				return nil, ErrSameVersionDigestConflict
			}
			rows = append(rows, map[string]string{"objectType": fmt.Sprint(want["objectType"]), "objectId": fmt.Sprint(want["objectId"]), "documentDigest": gd})
		}
		sort.Slice(rows, func(i, j int) bool { return rows[i]["objectId"] < rows[j]["objectId"] })
		digest, _ := rt.CreatorCanonicalDigest(rows, "")
		evidence = append(evidence, rt.ReleaseQueryClassEvidence{QueryClass: class, ObjectSetDigest: s.ObjectSetDigest(), DocumentsDigest: digest})
	}
	queries, err := c.verifyReleaseProductionQueries(ctx, b, s, expected, evidence[0].DocumentsDigest)
	if err != nil {
		return nil, err
	}
	return append(queries, evidence...), nil
}
