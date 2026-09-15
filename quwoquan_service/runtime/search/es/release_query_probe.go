package es

import (
	"context"
	"fmt"
	rt "quwoquan_service/runtime/search"
	"strings"
)

// 候选验证仍调用生产Backend/QueryBuilder，只在Provider请求前额外限定待准备slice。
// 不改业务匹配/排序/分页算法，也不从live读取或写refresh。
type exactReleaseSearcher struct {
	client  *Client
	binding rt.ReleaseQueryPreparationBinding
}

func (s exactReleaseSearcher) Search(ctx context.Context, index string, body map[string]any) ([]rt.RecallCandidate, error) {
	body["query"] = map[string]any{"bool": map[string]any{"must": []any{body["query"]}, "filter": []any{ReleaseBindingFilter(s.binding)}}}
	return s.client.Search(ctx, index, body)
}
func (c *Client) verifyReleaseProductionQueries(ctx context.Context, b rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot, expected map[string]map[string]any, documentsDigest string) ([]rt.ReleaseQueryClassEvidence, error) {
	backend := NewBackend(exactReleaseSearcher{c, b}, c.IndexName())
	ctx = WithReleaseBinding(ctx, &b)
	rows := []rt.ReleaseQueryClassEvidence{}
	// result/suggest/retrieval在SearchService.execute中仅有上限和调用者授权差异；共同执行Retrieve。
	// 三者各自遍历生产prefix分页，校验全部源映射，避免首屏假绿。
	for _, class := range []string{"result", "suggest", "retrieval", "ids"} {
		pageSize := 20
		if class == "suggest" {
			pageSize = 12
		}
		seen := map[string]bool{}
		var previous *rt.RetrieveHit
		for offset := 0; offset < len(expected) || offset == 0; offset += pageSize {
			req := rt.RetrieveRequest{Page: rt.PageRequest{Limit: pageSize, Offset: offset}}
			if class == "ids" {
				for _, id := range s.Identities() {
					req.IDs = append(req.IDs, id.ObjectID)
				}
			}
			response, err := rt.Retrieve(ctx, req, backend, rt.Viewer{})
			if err != nil {
				return nil, err
			}
			// facet是生产rankAndMerge对本次recall prefix的目标聚合，不是自造objectId terms聚合。
			facetCount := 0
			expectedTargets := map[string]bool{}
			for _, source := range expected {
				expectedTargets[string(rt.TargetForDocument(IndexToDocument(source)))] = true
			}
			seenFacets := map[string]bool{}
			for _, facet := range response.Facets {
				if !expectedTargets[facet.Key] || seenFacets[facet.Key] {
					return nil, ErrSameVersionDigestConflict
				}
				seenFacets[facet.Key] = true
				if facet.Count < 0 {
					return nil, ErrSameVersionDigestConflict
				}
				facetCount += facet.Count
			}
			wantPrefix := offset + pageSize
			if wantPrefix > len(expected) {
				wantPrefix = len(expected)
			}
			if facetCount != wantPrefix {
				return nil, fmt.Errorf("%w: production facet/count mismatch", ErrSameVersionDigestConflict)
			}
			for _, hit := range response.Hits {
				key := hit.ObjectType + ":" + hit.ObjectID
				if seen[key] {
					return nil, fmt.Errorf("%w: duplicate production page hit", ErrSameVersionDigestConflict)
				}
				seen[key] = true
				var want rt.Document
				found := false
				for _, source := range expected {
					if source["objectType"] == hit.ObjectType && source["objectId"] == hit.ObjectID {
						want = IndexToDocument(source)
						found = true
						break
					}
				}
				if !found || hit.Title != want.Title || hit.DeepLink != want.DeepLink {
					return nil, fmt.Errorf("%w: production hit mapping drift", ErrSameVersionDigestConflict)
				}
				if previous != nil && rt.LessHitStable(hit, *previous) {
					return nil, fmt.Errorf("production page order drift")
				}
				copyHit := hit
				previous = &copyHit
			}
			if len(response.Hits) == 0 {
				break
			}
		}
		if len(seen) != len(expected) {
			return nil, fmt.Errorf("%w: production pagination incomplete", ErrDependencyUnavailable)
		}
		// query-first文本及tag/target硬过滤直接使用同一生产请求路径。
		for _, source := range expected {
			doc := IndexToDocument(source)
			terms := rt.SplitQueryTerms(strings.TrimSpace(doc.Title))
			if len(terms) == 0 {
				continue
			}
			request := rt.RetrieveRequest{Targets: []rt.Target{rt.TargetForDocument(doc)}, Terms: terms, IDs: []string{doc.ObjectID}, Page: rt.PageRequest{Limit: 1000}}
			if len(doc.Tags) > 0 {
				request.Filters.Tags = []string{doc.Tags[0]}
			}
			response, err := rt.Retrieve(ctx, request, backend, rt.Viewer{})
			if err != nil {
				return nil, err
			}
			matched := false
			for _, hit := range response.Hits {
				if hit.ObjectID == doc.ObjectID && hit.ObjectType == doc.ObjectType {
					matched = true
				}
			}
			if !matched {
				return nil, fmt.Errorf("%w: query/filter cannot retrieve declared object", ErrDependencyUnavailable)
			}
		}
		rows = append(rows, rt.ReleaseQueryClassEvidence{QueryClass: class, ObjectSetDigest: s.ObjectSetDigest(), DocumentsDigest: documentsDigest})
	}
	return rows, nil
}
