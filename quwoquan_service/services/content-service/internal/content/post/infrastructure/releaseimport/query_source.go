package releaseimport

import (
	"context"
	"fmt"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	rt "quwoquan_service/runtime/search"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"time"
)

type HomepageSource interface {
	ReadHomepageCandidate(context.Context, rt.ReleaseCandidateBinding) (rt.ReleaseHomepageCandidateSnapshot, error)
}
type PostCandidateReader struct {
	database  *mongo.Database
	homepages HomepageSource
}

func NewPostCandidateReader(db *mongo.Database, homepages HomepageSource) *PostCandidateReader {
	return &PostCandidateReader{db, homepages}
}
func (r *PostCandidateReader) ReadPostCandidate(ctx context.Context, b rt.ReleaseCandidateBinding) (rt.ReleasePostCandidateSnapshot, error) {
	result, err := r.readCandidateSource(ctx, b)
	if err != nil {
		return result, err
	}
	if err = checkCandidateSafety(ctx, r.database, b, result.SnapshotDigest, false); err != nil {
		return rt.ReleasePostCandidateSnapshot{}, err
	}
	return result, nil
}

// 仅owner可信stage可先构造源再封存安全绑定；公开query不可绕过安全校验。
func (r *PostCandidateReader) readCandidateSource(ctx context.Context, b rt.ReleaseCandidateBinding) (rt.ReleasePostCandidateSnapshot, error) {
	result := rt.ReleasePostCandidateSnapshot{Release: b, Posts: []rt.ReleasePostPublicSnapshot{}}
	var state VerifiedImportedPostReleaseCandidate
	var err error
	if mongo.SessionFromContext(ctx) != nil {
		// stage已在进入事务前核验索引；Mongo禁止在事务内listIndexes。
		var stored importedReleaseCandidateState
		err = r.database.Collection("data_release_state").FindOne(ctx, bson.M{"kind": releaseCandidateKind, "environment": b.Environment, "sourceOwner": b.SourceOwner, "releaseId": b.ReleaseID, "manifestDigest": b.ManifestDigest}).Decode(&stored)
		if err == nil {
			err = validateVerifiedCandidateState(stored, b.Environment, b.SourceOwner, b.ReleaseID, b.ManifestDigest)
		}
		if err == nil {
			err = validateStoredCandidateClosure(ctx, r.database.Collection("data_release_candidate_posts"), r.database.Collection("data_release_candidate_outbox"), r.database.Collection("data_release_candidate_media_assets"), stored)
		}
		if err == nil {
			state = verifiedImportedPostReleaseCandidate(stored)
		}
	} else {
		state, err = ReadVerifiedImportedPostReleaseCandidate(ctx, r.database, b.Environment, b.SourceOwner, b.ReleaseID, b.ManifestDigest)
	}
	if err != nil {
		return result, err
	}
	if !state.Found || state.Counts.PostsExpected > 1000 {
		return result, fmt.Errorf("verified Post candidate not ready")
	}
	result.SourceClosureDigest = state.ClosureDigests.Posts
	result.MediaClosureDigest = state.ClosureDigests.Media
	homes := map[string]rt.ReleaseHomepagePublicSnapshot{}
	if r.homepages != nil {
		source, err := r.homepages.ReadHomepageCandidate(ctx, b)
		if err != nil {
			return result, err
		}
		if source.Validate() != nil {
			return result, rt.ErrCreatorSourceInvalid
		}
		for _, h := range source.Homepages {
			homes[h.Identity.ObjectID] = h
		}
	}
	filter := bson.M{"environment": b.Environment, "sourceOwner": b.SourceOwner, "releaseId": b.ReleaseID, "manifestDigest": b.ManifestDigest}
	cursor, err := r.database.Collection("data_release_candidate_posts").Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "postId", Value: 1}}).SetLimit(1001))
	if err != nil {
		return result, err
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var document bson.M
		if err = cursor.Decode(&document); err != nil {
			return result, err
		}
		digest, err := canonicalDocumentDigest(document, "documentDigest")
		if err != nil || digest != document["documentDigest"] {
			return result, rt.ErrCreatorSourceInvalid
		}
		raw, _ := bson.Marshal(document)
		var p postmodel.Post
		if err = bson.Unmarshal(raw, &p); err != nil {
			return result, err
		}
		id, _ := document["postId"].(string)
		postRef, _ := document["postRef"].(string)
		v := rt.ReleasePostPublicSnapshot{Identity: rt.ReleaseCandidateObjectIdentity{Release: b, ObjectType: "content.post", ObjectID: id, SourceVersion: state.ProjectionVersion, SourceDigest: digest}, PostRef: postRef, AuthorID: p.AuthorId, AuthorDisplayName: p.AuthorDisplayNameSnapshot, AuthorAvatarURL: sourceText(p.AuthorAvatarUrlSnapshot), ContentType: p.ContentType, Status: p.Status, Visibility: p.Visibility, ModerationStatus: p.ModerationStatus, Title: p.Title, Body: p.Body, Summary: p.Summary, TagRefs: append([]string{}, p.TagRefs...), EntityRefs: append([]string{}, p.EntityRefs...), MediaAssetIDs: append([]string{}, p.MediaAssetIds...), MediaURLs: append([]string{}, p.MediaUrls...), CoverURL: sourceText(p.CoverUrl), ThumbnailURL: sourceText(p.ThumbnailUrl), VideoURL: sourceText(p.VideoUrl), DurationMs: p.DurationMs, Width: int(p.Width), Height: int(p.Height), ContentVertical: sourceText(p.ContentVertical), PublishedAt: p.PublishedAt.UTC().Format(time.RFC3339Nano), UpdatedAt: p.UpdatedAt.UTC().Format(time.RFC3339Nano), DeepLink: "quwoquan://content/post/" + id}
		if p.PrimaryHomepageId != "" {
			h, ok := homes[p.PrimaryHomepageId]
			if !ok {
				return result, fmt.Errorf("exact Homepage source missing")
			}
			v.PrimaryHomepage = &h
		}
		result.Posts = append(result.Posts, v)
	}
	if err = cursor.Err(); err != nil {
		return result, err
	}
	if len(result.Posts) != state.Counts.PostsExpected {
		return result, rt.ErrCreatorSourceInvalid
	}
	if err = result.Seal(); err != nil {
		return result, err
	}
	return result, result.Validate()
}
func sourceText(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
