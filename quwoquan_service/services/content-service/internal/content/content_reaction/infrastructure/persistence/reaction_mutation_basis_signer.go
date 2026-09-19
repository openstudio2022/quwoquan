package persistence

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	"strings"
	"time"
)

const reactionBasisDomain = "quwoquan.content.content_reaction.mutation_basis.v1"

var (
	ErrReactionBasisInvalid = errors.New("content reaction basis invalid")
	ErrReactionBasisExpired = errors.New("content reaction basis expired")
)

type ReactionMutationBasisKey struct {
	ID       string
	Material []byte
}
type ReactionMutationBasisSigner struct {
	active   string
	keys     map[string][]byte
	audience string
	now      func() time.Time
}
type reactionBasisWire struct {
	Audience        string    `json:"aud"`
	TargetKind      string    `json:"tk"`
	TargetID        string    `json:"tid"`
	ActorDimension  string    `json:"ad"`
	ActorID         string    `json:"aid"`
	ExpectedVersion int64     `json:"ver"`
	Allowed         []string  `json:"allowed"`
	IssuedAt        time.Time `json:"iat"`
	AcceptUntil     time.Time `json:"exp"`
}

func NewReactionMutationBasisSigner(audience, active string, keys []ReactionMutationBasisKey) (*ReactionMutationBasisSigner, error) {
	if strings.TrimSpace(audience) == "" || strings.TrimSpace(active) == "" {
		return nil, ErrReactionBasisInvalid
	}
	m := map[string][]byte{}
	for _, k := range keys {
		if len(k.Material) < 32 {
			return nil, ErrReactionBasisInvalid
		}
		m[k.ID] = append([]byte(nil), k.Material...)
	}
	if len(m[active]) == 0 {
		return nil, ErrReactionBasisInvalid
	}
	return &ReactionMutationBasisSigner{active: active, keys: m, audience: audience, now: func() time.Time { return time.Now().UTC() }}, nil
}
func (s *ReactionMutationBasisSigner) WithClock(now func() time.Time) *ReactionMutationBasisSigner {
	if now != nil {
		s.now = now
	}
	return s
}
func (s *ReactionMutationBasisSigner) Issue(c reactionapp.MutationBasisClaims) (string, error) {
	c.IssuedAt = s.now().UTC()
	c.AcceptUntil = c.IssuedAt.Add(72 * time.Hour)
	allowed := make([]string, len(c.AllowedValues))
	for i, v := range c.AllowedValues {
		allowed[i] = string(v)
	}
	w := reactionBasisWire{Audience: s.audience, TargetKind: string(c.Identity.Target.Kind), TargetID: c.Identity.Target.ID, ActorDimension: string(c.Identity.Actor.Dimension), ActorID: c.Identity.Actor.ID, ExpectedVersion: c.ExpectedVersion, Allowed: allowed, IssuedAt: c.IssuedAt, AcceptUntil: c.AcceptUntil}
	b, err := json.Marshal(w)
	if err != nil {
		return "", err
	}
	sig := s.sign(s.active, b)
	return s.active + "." + base64.RawURLEncoding.EncodeToString(b) + "." + base64.RawURLEncoding.EncodeToString(sig), nil
}
func (s *ReactionMutationBasisSigner) Verify(t string, i reactiondomain.Identity, v reactiondomain.Value, ver int64) (reactionapp.MutationBasisClaims, error) {
	return s.verify(t, i, v, ver, false)
}
func (s *ReactionMutationBasisSigner) VerifyForRecovery(t string, i reactiondomain.Identity, v reactiondomain.Value, ver int64) (reactionapp.MutationBasisClaims, error) {
	return s.verify(t, i, v, ver, true)
}
func (s *ReactionMutationBasisSigner) verify(t string, i reactiondomain.Identity, v reactiondomain.Value, ver int64, expired bool) (reactionapp.MutationBasisClaims, error) {
	p := strings.Split(strings.TrimSpace(t), ".")
	if len(p) != 3 || len(s.keys[p[0]]) == 0 {
		return reactionapp.MutationBasisClaims{}, ErrReactionBasisInvalid
	}
	b, e := base64.RawURLEncoding.DecodeString(p[1])
	if e != nil {
		return reactionapp.MutationBasisClaims{}, ErrReactionBasisInvalid
	}
	sig, e := base64.RawURLEncoding.DecodeString(p[2])
	if e != nil || !hmac.Equal(sig, s.sign(p[0], b)) {
		return reactionapp.MutationBasisClaims{}, ErrReactionBasisInvalid
	}
	var w reactionBasisWire
	if json.Unmarshal(b, &w) != nil || w.Audience != s.audience || w.TargetKind != string(i.Target.Kind) || w.TargetID != i.Target.ID || w.ActorDimension != string(i.Actor.Dimension) || w.ActorID != i.Actor.ID || w.ExpectedVersion != ver || w.AcceptUntil.Sub(w.IssuedAt) > 72*time.Hour {
		return reactionapp.MutationBasisClaims{}, ErrReactionBasisInvalid
	}
	ok := false
	allowed := make([]reactiondomain.Value, len(w.Allowed))
	for x, a := range w.Allowed {
		allowed[x] = reactiondomain.Value(a)
		if allowed[x] == v {
			ok = true
		}
	}
	if !ok {
		return reactionapp.MutationBasisClaims{}, ErrReactionBasisInvalid
	}
	if !expired && !s.now().UTC().Before(w.AcceptUntil) {
		return reactionapp.MutationBasisClaims{}, ErrReactionBasisExpired
	}
	return reactionapp.MutationBasisClaims{Identity: i, ExpectedVersion: w.ExpectedVersion, AllowedValues: allowed, IssuedAt: w.IssuedAt, AcceptUntil: w.AcceptUntil}, nil
}
func (s *ReactionMutationBasisSigner) Digest(t string) string {
	h := sha256.Sum256([]byte(reactionBasisDomain + "\x1f" + strings.TrimSpace(t)))
	return hex.EncodeToString(h[:])
}
func (s *ReactionMutationBasisSigner) sign(id string, b []byte) []byte {
	m := hmac.New(sha256.New, s.keys[id])
	m.Write([]byte(reactionBasisDomain))
	m.Write([]byte{31})
	m.Write([]byte(id))
	m.Write([]byte{31})
	m.Write(b)
	return m.Sum(nil)
}
