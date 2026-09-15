package safety

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"sort"
	"strings"
	"time"
)

const Collection = "post_safety_states"

type Manager struct {
	collection  *mongo.Collection
	environment string
	key         []byte
	authority   app.PostSafetyAuthority
}
type state struct {
	ObjectDigest string    `bson:"objectDigest"`
	ScopeDigest  string    `bson:"scopeDigest"`
	Revision     int64     `bson:"safetyRevision"`
	Generation   int64     `bson:"fenceGeneration"`
	State        string    `bson:"state"`
	Version      int64     `bson:"sourceVersion"`
	Digest       string    `bson:"decisionDigest"`
	Reason       string    `bson:"reason"`
	DecidedAt    time.Time `bson:"decidedAt"`
}

func New(db *mongo.Database, environment string, key []byte, authority app.PostSafetyAuthority) (*Manager, error) {
	if db == nil || len(key) < 32 || authority == nil || environment == "" {
		return nil, app.ErrPostSafetyNotReady
	}
	return &Manager{db.Collection(Collection), environment, append([]byte{}, key...), authority}, nil
}
func (m *Manager) EnsureIndexes(ctx context.Context) error {
	if err := m.authority.VerifyRecovery(ctx); err != nil {
		return err
	}
	_, err := m.collection.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "objectDigest", Value: 1}}, Options: options.Index().SetName("uq_post_safety_object").SetUnique(true)})
	return err
}
func (m *Manager) hash(values ...string) string {
	raw, _ := json.Marshal(values)
	mac := hmac.New(sha256.New, m.key)
	_, _ = mac.Write(raw)
	return "sha256:" + hex.EncodeToString(mac.Sum(nil))
}
func (m *Manager) Identity(owner, id string) (string, error) {
	if m == nil || id == "" || (owner != "qwq_data" && owner != "content") {
		return "", app.ErrPostSafetyConflict
	}
	return m.hash("post-safety-object", m.environment, owner, "content.post", id), nil
}
func transaction(ctx context.Context) error {
	if mongo.SessionFromContext(ctx) == nil {
		return app.ErrPostSafetyNotReady
	}
	return nil
}
func (m *Manager) Initialize(ctx context.Context, owner, id string, version int64, status, reason, digest string) (app.PostSafetyMember, error) {
	if err := transaction(ctx); err != nil {
		return app.PostSafetyMember{}, err
	}
	if err := m.authority.VerifyRecovery(ctx); err != nil {
		return app.PostSafetyMember{}, err
	}
	if owner != "content" {
		if err := m.authority.VerifySource(ctx, m.environment, owner, id); err != nil {
			return app.PostSafetyMember{}, err
		}
	}
	key, err := m.Identity(owner, id)
	if err != nil || version <= 0 || (status != "allowed" && status != "restricted") || !validDigest(digest) {
		return app.PostSafetyMember{}, app.ErrPostSafetyConflict
	}
	current, err := m.load(ctx, key)
	if err == nil {
		if current.State != "allowed" || status != "allowed" {
			return app.PostSafetyMember{}, app.ErrPostSafetyNotReady
		}
		member := app.PostSafetyMember{ObjectDigest: key, SafetyRevision: current.Revision}
		if err = m.TouchAllowed(ctx, []app.PostSafetyMember{member}); err != nil {
			return app.PostSafetyMember{}, err
		}
		return member, nil
	}
	if !errors.Is(err, mongo.ErrNoDocuments) {
		return app.PostSafetyMember{}, err
	}
	_, err = m.collection.InsertOne(ctx, state{key, m.hash("post-safety-scope", m.environment, owner), 1, 1, status, version, digest, reason, time.Now().UTC()})
	if err != nil {
		return app.PostSafetyMember{}, err
	}
	return app.PostSafetyMember{ObjectDigest: key, SafetyRevision: 1}, nil
}
func validDigest(s string) bool {
	if len(s) != 71 || !strings.HasPrefix(s, "sha256:") {
		return false
	}
	_, e := hex.DecodeString(s[7:])
	return e == nil
}
func (m *Manager) load(ctx context.Context, key string) (state, error) {
	var s state
	err := m.collection.FindOne(ctx, bson.M{"objectDigest": key}).Decode(&s)
	if err == nil && (s.Revision < 1 || s.Generation < 1 || s.Version < 1 || !validDigest(s.Digest) || s.DecidedAt.IsZero() || (s.State != "allowed" && s.State != "restricted" && s.State != "terminated")) {
		err = app.ErrPostSafetyConflict
	}
	return s, err
}
func (m *Manager) LoadRevision(ctx context.Context, owner, id string) (app.PostSafetyMember, error) {
	if err := m.authority.VerifyRecovery(ctx); err != nil {
		return app.PostSafetyMember{}, err
	}
	key, err := m.Identity(owner, id)
	if err != nil {
		return app.PostSafetyMember{}, err
	}
	s, err := m.load(ctx, key)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return app.PostSafetyMember{}, app.ErrPostSafetyNotReady
	}
	if err != nil {
		return app.PostSafetyMember{}, err
	}
	return app.PostSafetyMember{ObjectDigest: key, SafetyRevision: s.Revision}, nil
}

func (m *Manager) Read(ctx context.Context, owner, id string) (app.PostSafetyMember, error) {
	if err := m.authority.VerifyRecovery(ctx); err != nil {
		return app.PostSafetyMember{}, err
	}
	key, err := m.Identity(owner, id)
	if err != nil {
		return app.PostSafetyMember{}, err
	}
	s, err := m.load(ctx, key)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return app.PostSafetyMember{}, app.ErrPostSafetyNotReady
	}
	if err != nil {
		return app.PostSafetyMember{}, err
	}
	if s.State != "allowed" {
		return app.PostSafetyMember{}, app.ErrPostSafetyNotReady
	}
	return app.PostSafetyMember{ObjectDigest: key, SafetyRevision: s.Revision}, nil
}
func (m *Manager) TouchAllowed(ctx context.Context, members []app.PostSafetyMember) error {
	if err := transaction(ctx); err != nil {
		return err
	}
	if err := m.authority.VerifyRecovery(ctx); err != nil {
		return err
	}
	rows := append([]app.PostSafetyMember{}, members...)
	sort.Slice(rows, func(i, j int) bool { return rows[i].ObjectDigest < rows[j].ObjectDigest })
	for i, row := range rows {
		if !validDigest(row.ObjectDigest) || row.SafetyRevision < 1 || (i > 0 && rows[i-1].ObjectDigest == row.ObjectDigest) {
			return app.ErrPostSafetyConflict
		}
		result, err := m.collection.UpdateOne(ctx, bson.M{"objectDigest": row.ObjectDigest, "safetyRevision": row.SafetyRevision, "state": "allowed"}, bson.M{"$inc": bson.M{"fenceGeneration": int64(1)}})
		if err != nil {
			return err
		}
		if result.MatchedCount != 1 {
			return app.ErrPostSafetyNotReady
		}
	}
	return nil
}
func (m *Manager) Decide(ctx context.Context, owner, id string, expected, version int64, next, reason, digest string) (app.PostSafetyMember, error) {
	if err := transaction(ctx); err != nil {
		return app.PostSafetyMember{}, err
	}
	if err := m.authority.VerifyRecovery(ctx); err != nil {
		return app.PostSafetyMember{}, err
	}
	key, err := m.Identity(owner, id)
	if err != nil {
		return app.PostSafetyMember{}, err
	}
	s, err := m.load(ctx, key)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return app.PostSafetyMember{}, app.ErrPostSafetyNotReady
	}
	if err != nil {
		return app.PostSafetyMember{}, err
	}
	if s.Version == version && s.Digest == digest {
		return app.PostSafetyMember{ObjectDigest: key, SafetyRevision: s.Revision}, nil
	}
	if expected != s.Revision || version <= s.Version || !validDigest(digest) || (next != "allowed" && next != "restricted" && next != "terminated") || (s.State == "terminated" && next != "terminated") {
		return app.PostSafetyMember{}, app.ErrPostSafetyConflict
	}
	if next == "allowed" {
		if err = m.authority.VerifySource(ctx, m.environment, owner, id); err != nil {
			return app.PostSafetyMember{}, err
		}
	}
	revision := s.Revision
	if next != s.State {
		revision++
	}
	result, err := m.collection.UpdateOne(ctx, bson.M{"objectDigest": key, "safetyRevision": expected, "sourceVersion": s.Version}, bson.M{"$set": bson.M{"state": next, "reason": reason, "decisionDigest": digest, "sourceVersion": version, "safetyRevision": revision, "decidedAt": time.Now().UTC()}, "$inc": bson.M{"fenceGeneration": int64(1)}})
	if err != nil {
		return app.PostSafetyMember{}, err
	}
	if result.MatchedCount != 1 {
		return app.PostSafetyMember{}, app.ErrPostSafetyConflict
	}
	return app.PostSafetyMember{ObjectDigest: key, SafetyRevision: revision}, nil
}

var _ app.PostSafetyPort = (*Manager)(nil)

func (m *Manager) VerifySource(ctx context.Context, environment, owner, sourceID string) error {
	if environment != m.environment {
		return app.ErrPostSafetyConflict
	}
	return m.authority.VerifySource(ctx, environment, owner, sourceID)
}

var _ app.PostSafetySourceVerifier = (*Manager)(nil)
