package preparation_test

import (
	"context"
	"fmt"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/search-service/tests/support"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
// typed源fixture只验证Search，不冒充Content/Entity源真实性或Content CAS。
func TestUnifiedPostHomepagePartitionAndAllQueryClasses(t *testing.T) {
	t.Setenv("QWQ_TEST_ELASTICSEARCH_ENDPOINT", "")
	ctx, cancel := context.WithTimeout(t.Context(), 3*time.Minute)
	defer cancel()
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	defer stop()
	client, err := es.NewClient(es.Config{Endpoints: []string{endpoint}, Index: "unified_sources", RequestTimeout: 30 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if err = client.EnsureIndex(ctx); err != nil {
		t.Fatal(err)
	}
	digest := "sha256:" + strings.Repeat("a", 64)
	makeSource := func(releaseID, kind, title string) (rt.ReleaseQueryPreparationBinding, rt.SearchReleaseCandidateSnapshot) {
		b := rt.ReleaseQueryPreparationBinding{Release: rt.ReleaseCandidateBinding{"gamma", "qwq_data", releaseID, digest}, Slice: kind + "_search", ProviderBindingGeneration: digest, SchemaGeneration: client.SchemaGeneration()}
		identity := rt.ReleaseCandidateObjectIdentity{Release: b.Release, ObjectType: "content.post", ObjectID: "same-post", SourceVersion: 1, SourceDigest: digest}
		if kind == "post" {
			post := rt.ReleasePostPublicSnapshot{Identity: identity, PostRef: "posts/article/exact", AuthorID: "author", AuthorDisplayName: "作者", ContentType: "article", Status: "published", Visibility: "public", ModerationStatus: "approved", Title: title, TagRefs: []string{}, EntityRefs: []string{}, MediaAssetIDs: []string{}, MediaURLs: []string{}, PublishedAt: "2026-09-12T00:00:00Z", UpdatedAt: "2026-09-12T00:00:00Z", DeepLink: "quwoquan://content/posts/same-post"}
			s := rt.ReleasePostCandidateSnapshot{Release: b.Release, SourceClosureDigest: digest, MediaClosureDigest: digest, Posts: []rt.ReleasePostPublicSnapshot{post}}
			_ = s.Seal()
			return b, rt.SearchReleaseCandidateSnapshot{Kind: kind, Post: &s}
		}
		identity.ObjectType = "entity.homepage"
		identity.ObjectID = "same-home"
		home := rt.ReleaseHomepagePublicSnapshot{Identity: identity, EntityRef: "entities/place/example", CanonicalEntityID: "entity-example", Title: title, HomepageType: "sight", TagRefs: []string{}, UpdatedAt: "2026-09-12T00:00:00Z", DeepLink: "quwoquan://homepages/same-home"}
		s := rt.ReleaseHomepageCandidateSnapshot{Release: b.Release, SourceClosureDigest: digest, EntityRefMappingDigest: digest, Homepages: []rt.ReleaseHomepagePublicSnapshot{home}}
		_ = s.Seal()
		return b, rt.SearchReleaseCandidateSnapshot{Kind: kind, Homepage: &s}
	}
	for _, release := range []string{"a", "b"} {
		for _, kind := range []string{"post", "homepage"} {
			b, s := makeSource(release, kind, release+kind)
			if _, err = client.WriteReleaseCandidate(ctx, b, s); err != nil {
				t.Fatal(err)
			}
			deadline := time.Now().Add(10 * time.Second)
			for {
				classes, e := client.VerifyReleaseCandidate(ctx, b, s)
				if e == nil {
					if len(classes) != 6 {
						t.Fatal("missing classes")
					}
					break
				}
				if time.Now().After(deadline) {
					t.Fatal(e)
				}
				time.Sleep(100 * time.Millisecond)
			}
		}
	}
	_, err = es.NewIndexer(client, client.WriteIndexName()).ApplyVersioned(ctx, es.VersionedChangeEvent{Op: es.OpUpsert, SourceVersion: 1, Doc: rt.Document{ObjectType: "content.post", ObjectID: "ugc", Title: "ugc", Visibility: "public"}})
	if err != nil {
		t.Fatal(err)
	}
	time.Sleep(time.Second)
	for _, release := range []string{"a", "b", "a"} {
		b, _ := makeSource(release, "post", "")
		rows, e := es.NewBackend(client, client.IndexName()).Recall(es.WithReleaseBinding(ctx, &b), rt.RetrievePlan{Limit: 20})
		if e != nil || len(rows) != 3 {
			t.Fatal("partition/UGC mismatch", len(rows), e)
		}
		for _, row := range rows {
			if row.Document.ObjectID != "ugc" && !strings.HasPrefix(row.Document.Title, release) {
				t.Fatal("mixed release", row)
			}
		}
	}
	b, s := makeSource("a", "post", "apost")
	bad := b
	bad.SchemaGeneration = digest
	if _, err = client.VerifyReleaseCandidate(ctx, bad, s); err == nil {
		t.Fatal("schema drift accepted")
	}
	// 超过所有默认首屏，真实执行分页/排序、CJK文本与tag过滤。
	manyBinding, many := makeSource("many", "post", "洱海骑行攻略")
	template := many.Post.Posts[0]
	many.Post.Posts = nil
	for n := 0; n < 25; n++ {
		p := template
		p.Identity.ObjectID = fmt.Sprintf("page-%02d", n)
		p.PostRef = fmt.Sprintf("posts/article/page-%02d", n)
		p.DeepLink = "quwoquan://content/posts/" + p.Identity.ObjectID
		p.TagRefs = []string{"骑行"}
		many.Post.Posts = append(many.Post.Posts, p)
	}
	if e := many.Post.Seal(); e != nil {
		t.Fatal(e)
	}
	if _, e := client.WriteReleaseCandidate(ctx, manyBinding, many); e != nil {
		t.Fatal(e)
	}
	time.Sleep(time.Second)
	if _, e := client.VerifyReleaseCandidate(ctx, manyBinding, many); e != nil {
		t.Fatal("production CJK paginated queries", e)
	}
	// 同一binding额外对象不能靠top-N截断逃过集合审计。
	extra := many
	copied := *many.Post
	extra.Post = &copied
	extra.Post.Posts = append([]rt.ReleasePostPublicSnapshot{}, many.Post.Posts...)
	p := template
	p.Identity.ObjectID = "extra"
	p.PostRef = "posts/article/extra"
	p.DeepLink = "quwoquan://content/posts/extra"
	extra.Post.Posts = append(extra.Post.Posts, p)
	_ = extra.Post.Seal()
	if _, e := client.WriteReleaseCandidate(ctx, manyBinding, extra); e != nil {
		t.Fatal(e)
	}
	time.Sleep(time.Second)
	if _, e := client.VerifyReleaseCandidate(ctx, manyBinding, many); e == nil {
		t.Fatal("extra candidate accepted")
	}
	s.Post.Posts[0].Title = "tampered"
	if _, err = client.VerifyReleaseCandidate(ctx, b, s); err == nil {
		t.Fatal("source tamper accepted")
	}
}
