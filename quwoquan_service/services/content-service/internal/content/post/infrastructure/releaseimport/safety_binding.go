package releaseimport

import (
	"context"
	"encoding/json"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	rt "quwoquan_service/runtime/search"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/safety"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"sort"
	"time"
)

type CandidateSafetyReader struct {
	db          *mongo.Database
	environment string
}

func NewCandidateSafetyReader(db *mongo.Database, environment string) *CandidateSafetyReader {
	return &CandidateSafetyReader{db, environment}
}
func (r *CandidateSafetyReader) ReadSafety(ctx context.Context, q wire.ReadPostCandidateSafetyQuery) (wire.PostCandidateSafetyResult, error) {
	if r == nil || r.db == nil || q.Release.Environment != r.environment || q.Release.SourceOwner != "qwq_data" {
		return wire.PostCandidateSafetyResult{}, app.ErrPostSafetyConflict
	}
	b := rt.ReleaseCandidateBinding{Environment: q.Release.Environment, SourceOwner: q.Release.SourceOwner, ReleaseID: q.Release.ReleaseId, ManifestDigest: q.Release.ManifestDigest}
	if b.Validate() != nil || !sha256Pattern.MatchString(q.SnapshotDigest) {
		return wire.PostCandidateSafetyResult{}, app.ErrPostSafetyConflict
	}
	if err := checkCandidateSafety(ctx, r.db, b, q.SnapshotDigest, false); err != nil {
		return wire.PostCandidateSafetyResult{}, err
	}
	var row struct {
		Binding *wire.PostCandidateSafetyBinding `bson:"safetyBinding"`
	}
	if err := r.db.Collection("data_release_state").FindOne(ctx, bson.M{"kind": "candidate", "environment": b.Environment, "sourceOwner": b.SourceOwner, "releaseId": b.ReleaseID, "manifestDigest": b.ManifestDigest}).Decode(&row); err != nil {
		return wire.PostCandidateSafetyResult{}, err
	}
	if row.Binding == nil {
		return wire.PostCandidateSafetyResult{}, app.ErrPostSafetyNotReady
	}
	return wire.PostCandidateSafetyResult{Binding: *row.Binding, CheckedAt: time.Now().UTC()}, nil
}

// 明确注入Post owner安全端口，缺失不能自动allowed；不授予外部activation执行权。
type postSafetyContextKey struct{}

func WithPostSafety(ctx context.Context, port app.PostSafetyPort) context.Context {
	return context.WithValue(ctx, postSafetyContextKey{}, port)
}
func requiredPostSafety(ctx context.Context) (app.PostSafetyPort, error) {
	port, _ := ctx.Value(postSafetyContextKey{}).(app.PostSafetyPort)
	if port == nil {
		return nil, app.ErrPostSafetyNotReady
	}
	return port, nil
}
func candidateSafetyDigest(binding wire.PostCandidateSafetyBinding) string {
	d, _ := rt.CreatorCanonicalDigest(binding, "bindingDigest")
	return d
}

// 安全绑定封存在既有candidate控制行；source快照须由当前owner验证，不改源集合字节。
func sealCandidateSafety(ctx context.Context, db *mongo.Database, source rt.ReleasePostCandidateSnapshot) (wire.PostCandidateSafetyBinding, error) {
	result := wire.PostCandidateSafetyBinding{Release: wire.ReleaseCandidateBinding{Environment: source.Release.Environment, SourceOwner: source.Release.SourceOwner, ReleaseId: source.Release.ReleaseID, ManifestDigest: source.Release.ManifestDigest}, SnapshotDigest: source.SnapshotDigest, Members: []wire.PostCandidateSafetyMember{}}
	port, err := requiredPostSafety(ctx)
	if err != nil {
		return result, err
	}
	if mongo.SessionFromContext(ctx) == nil || source.Validate() != nil {
		return result, app.ErrPostSafetyConflict
	}
	for _, post := range source.Posts {
		member, e := port.Initialize(ctx, source.Release.SourceOwner, post.Identity.ObjectID, post.Identity.SourceVersion, "allowed", "verified_source", post.Identity.SourceDigest)
		if e != nil {
			return result, e
		}
		result.Members = append(result.Members, wire.PostCandidateSafetyMember{ObjectDigest: member.ObjectDigest, SafetyRevision: member.SafetyRevision})
	}
	sort.Slice(result.Members, func(i, j int) bool { return result.Members[i].ObjectDigest < result.Members[j].ObjectDigest })
	result.BindingDigest = candidateSafetyDigest(result)
	filter := bson.M{"kind": "candidate", "environment": source.Release.Environment, "sourceOwner": source.Release.SourceOwner, "releaseId": source.Release.ReleaseID, "manifestDigest": source.Release.ManifestDigest}
	var prior struct {
		Binding *wire.PostCandidateSafetyBinding `bson:"safetyBinding"`
	}
	if err = db.Collection("data_release_state").FindOne(ctx, filter).Decode(&prior); err != nil {
		return result, err
	}
	if prior.Binding != nil {
		raw, _ := json.Marshal(prior.Binding)
		expected, _ := json.Marshal(result)
		if string(raw) != string(expected) {
			return result, app.ErrPostSafetyConflict
		}
		return result, nil
	}
	filter["safetyBinding"] = bson.M{"$exists": false}
	update, err := db.Collection("data_release_state").UpdateOne(ctx, filter, bson.M{"$set": bson.M{"safetyBinding": result}})
	if err != nil {
		return result, err
	}
	if update.MatchedCount != 1 {
		return result, app.ErrPostSafetyConflict
	}
	return result, nil
}
func checkCandidateSafety(ctx context.Context, db *mongo.Database, b rt.ReleaseCandidateBinding, snapshot string, touch bool) error {
	port, err := requiredPostSafety(ctx)
	if err != nil {
		return err
	}
	var row struct {
		Binding *wire.PostCandidateSafetyBinding `bson:"safetyBinding"`
	}
	filter := bson.M{"environment": b.Environment, "sourceOwner": b.SourceOwner, "releaseId": b.ReleaseID, "manifestDigest": b.ManifestDigest}
	stateFilter := bson.M{}
	for k, v := range filter {
		stateFilter[k] = v
	}
	stateFilter["kind"] = "candidate"
	if err = db.Collection("data_release_state").FindOne(ctx, stateFilter).Decode(&row); err != nil {
		return err
	}
	if row.Binding == nil {
		return app.ErrPostSafetyNotReady
	}
	value := *row.Binding
	if value.Release.Environment != b.Environment || value.Release.SourceOwner != b.SourceOwner || value.Release.ReleaseId != b.ReleaseID || value.Release.ManifestDigest != b.ManifestDigest || value.BindingDigest != candidateSafetyDigest(value) || (snapshot != "" && value.SnapshotDigest != snapshot) {
		return app.ErrPostSafetyConflict
	}
	cur, err := db.Collection("data_release_candidate_posts").Find(ctx, filter, options.Find().SetProjection(bson.M{"postId": 1}).SetLimit(1001))
	if err != nil {
		return err
	}
	defer cur.Close(ctx)
	members := []app.PostSafetyMember{}
	for cur.Next(ctx) {
		var post struct {
			ID string `bson:"postId"`
		}
		if err = cur.Decode(&post); err != nil {
			return err
		}
		member, e := port.Read(ctx, b.SourceOwner, post.ID)
		if e != nil {
			return e
		}
		members = append(members, member)
	}
	if err = cur.Err(); err != nil {
		return err
	}
	sort.Slice(members, func(i, j int) bool { return members[i].ObjectDigest < members[j].ObjectDigest })
	if len(members) != len(value.Members) || len(members) > 1000 {
		return app.ErrPostSafetyConflict
	}
	for i, member := range members {
		if member.ObjectDigest != value.Members[i].ObjectDigest || member.SafetyRevision != value.Members[i].SafetyRevision {
			return app.ErrPostSafetyNotReady
		}
	}
	if touch {
		return port.TouchAllowed(ctx, members)
	}
	return nil
}
