package persistence

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

const (
	// basisSignatureDomain 是本签名用途的 domain separation 标签。
	// 它不复用 access-token 密钥，也不与其他签名面共享消息空间。
	basisSignatureDomain = "quwoquan.user.persona_relationship.mutation_basis.v1"

	// basisAcceptWindow 是依据的最长接受窗口。超过它只拒绝新接纳。
	basisAcceptWindow = 72 * time.Hour

	// basisMinimumKeyBytes 拒绝过短的签名材料；配置错误必须启动即失败。
	basisMinimumKeyBytes = 32
)

var (
	// ErrBasisRequired 表示命令缺少写依据。
	ErrBasisRequired = errors.New("persona relationship mutation basis is required")
	// ErrBasisInvalid 表示依据被篡改、换主体/目标/版本，或签名不匹配。
	ErrBasisInvalid = errors.New("persona relationship mutation basis is invalid")
	// ErrBasisExpired 表示依据已超过服务端签发的接受期限。
	ErrBasisExpired = errors.New("persona relationship mutation basis has expired")
)

type mutationBasisWire struct {
	Audience        string                 `json:"aud"`
	ActorPersonaID  string                 `json:"act"`
	TargetPersonaID string                 `json:"tgt"`
	TargetKind      string                 `json:"tkd"`
	PairID          string                 `json:"pid"`
	ExpectedVersion int64                  `json:"ver"`
	AllowedActions  []relmodel.CommandKind `json:"acts"`
	IssuedAt        time.Time              `json:"iat"`
	AcceptUntil     time.Time              `json:"exp"`
}

// MutationBasisSigner 用受管独立用途密钥签发与验签写依据。
// 验签密钥集合覆盖最大写窗口，使轮换期间已签发的依据仍可验证。
type MutationBasisSigner struct {
	activeKeyID    string
	keysByID       map[string][]byte
	audience       string
	now            func() time.Time
	acceptDuration time.Duration
}

// MutationBasisKey 是一个受管签名密钥；material 只允许仓外注入。
type MutationBasisKey struct {
	ID       string
	Material []byte
}

func NewMutationBasisSigner(
	audience string,
	activeKeyID string,
	keys []MutationBasisKey,
) (*MutationBasisSigner, error) {
	audience = strings.TrimSpace(audience)
	activeKeyID = strings.TrimSpace(activeKeyID)
	if audience == "" {
		return nil, errors.New("mutation basis audience is required")
	}
	if activeKeyID == "" {
		return nil, errors.New("mutation basis active key id is required")
	}
	keysByID := make(map[string][]byte, len(keys))
	for _, key := range keys {
		id := strings.TrimSpace(key.ID)
		if id == "" {
			return nil, errors.New("mutation basis key id is required")
		}
		if len(key.Material) < basisMinimumKeyBytes {
			return nil, fmt.Errorf(
				"mutation basis key %q must carry at least %d bytes",
				id, basisMinimumKeyBytes,
			)
		}
		keysByID[id] = key.Material
	}
	if _, ok := keysByID[activeKeyID]; !ok {
		return nil, fmt.Errorf("mutation basis active key %q is not in the keyring", activeKeyID)
	}
	return &MutationBasisSigner{
		activeKeyID:    activeKeyID,
		keysByID:       keysByID,
		audience:       audience,
		now:            func() time.Time { return time.Now().UTC() },
		acceptDuration: basisAcceptWindow,
	}, nil
}

// WithClock 只用于测试注入固定时钟。
func (s *MutationBasisSigner) WithClock(now func() time.Time) *MutationBasisSigner {
	if now != nil {
		s.now = now
	}
	return s
}

// Issue 为一次读取签发写依据。期限由服务端决定，调用方不能延长。
func (s *MutationBasisSigner) Issue(claims relationshipapp.MutationBasisClaims) (string, error) {
	issuedAt := s.now().UTC()
	claims.IssuedAt = issuedAt
	claims.AcceptUntil = issuedAt.Add(s.acceptDuration)
	if strings.TrimSpace(claims.ActorPersonaID) == "" ||
		strings.TrimSpace(claims.TargetPersonaID) == "" ||
		strings.TrimSpace(claims.PairID) == "" {
		return "", errors.New("mutation basis requires actor, target and pair identity")
	}
	if len(claims.AllowedActions) == 0 {
		return "", errors.New("mutation basis requires at least one allowed action")
	}
	payload, err := json.Marshal(mutationBasisWire{Audience: s.audience, ActorPersonaID: claims.ActorPersonaID, TargetPersonaID: claims.TargetPersonaID, TargetKind: claims.TargetKind, PairID: claims.PairID, ExpectedVersion: claims.ExpectedVersion, AllowedActions: claims.AllowedActions, IssuedAt: claims.IssuedAt, AcceptUntil: claims.AcceptUntil})
	if err != nil {
		return "", fmt.Errorf("marshal mutation basis claims: %w", err)
	}
	signature := s.sign(s.activeKeyID, payload)
	return strings.Join([]string{
		s.activeKeyID,
		base64.RawURLEncoding.EncodeToString(payload),
		base64.RawURLEncoding.EncodeToString(signature),
	}, "."), nil
}

// Verify 验签并核对依据是否授权本次命令。
// 换 actor、换 target、改版本、改期限或换用其它操作都返回 ErrBasisInvalid；
// 过期返回 ErrBasisExpired，且不因重试而刷新。
func (s *MutationBasisSigner) Verify(token string, command relmodel.Command, pairID string) (relationshipapp.MutationBasisClaims, error) {
	return s.verify(token, command, pairID, false)
}

func (s *MutationBasisSigner) VerifyForRecovery(token string, command relmodel.Command, pairID string) (relationshipapp.MutationBasisClaims, error) {
	return s.verify(token, command, pairID, true)
}

func (s *MutationBasisSigner) verify(
	token string,
	command relmodel.Command,
	pairID string,
	allowExpired bool,
) (relationshipapp.MutationBasisClaims, error) {
	token = strings.TrimSpace(token)
	if token == "" {
		return relationshipapp.MutationBasisClaims{}, ErrBasisRequired
	}
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	material, ok := s.keysByID[parts[0]]
	if !ok || len(material) == 0 {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	if !hmac.Equal(signature, s.sign(parts[0], payload)) {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	var wire mutationBasisWire
	if err := json.Unmarshal(payload, &wire); err != nil {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	if wire.Audience != s.audience {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	claims := relationshipapp.MutationBasisClaims{ActorPersonaID: wire.ActorPersonaID, TargetPersonaID: wire.TargetPersonaID, TargetKind: wire.TargetKind, PairID: wire.PairID, ExpectedVersion: wire.ExpectedVersion, AllowedActions: wire.AllowedActions, IssuedAt: wire.IssuedAt, AcceptUntil: wire.AcceptUntil}
	if claims.ActorPersonaID != strings.TrimSpace(command.SourcePersonaID) ||
		claims.TargetPersonaID != strings.TrimSpace(command.TargetPersonaID) ||
		claims.PairID != strings.TrimSpace(pairID) {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	if !basisAllowsAction(claims.AllowedActions, command.Kind) {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	if command.ExpectedVersion == nil || *command.ExpectedVersion != claims.ExpectedVersion {
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	if claims.AcceptUntil.Sub(claims.IssuedAt) > s.acceptDuration {
		// 自报的超长期限一律无效，即使签名有效也不接受。
		return relationshipapp.MutationBasisClaims{}, ErrBasisInvalid
	}
	if !allowExpired && !s.now().UTC().Before(claims.AcceptUntil) {
		return relationshipapp.MutationBasisClaims{}, ErrBasisExpired
	}
	return claims, nil
}

// ReadCursorSigner 从同一受管 keyring 派生独立用途的读游标密钥。domain
// separation 保证游标签名不能作为 mutation basis，轮换行为与写依据一致。
func (s *MutationBasisSigner) ReadCursorSigner() *relationshipapp.ReadCursorSigner {
	mac := hmac.New(sha256.New, s.keysByID[s.activeKeyID])
	mac.Write([]byte("quwoquan.user.persona_relationship.read_cursor.key.v1\x1f"))
	mac.Write([]byte(s.activeKeyID))
	material := mac.Sum(nil)
	signer, err := relationshipapp.NewReadCursorSigner(material)
	if err != nil {
		panic("derive relationship read cursor signer: " + err.Error())
	}
	return signer
}

// Digest 返回依据的稳定摘要，用于绑定 receipt 而不落原文。
func (s *MutationBasisSigner) Digest(token string) string {
	digest := sha256.Sum256([]byte(basisSignatureDomain + "\x1f" + strings.TrimSpace(token)))
	return fmt.Sprintf("%x", digest[:])
}

func (s *MutationBasisSigner) sign(keyID string, payload []byte) []byte {
	mac := hmac.New(sha256.New, s.keysByID[keyID])
	mac.Write([]byte(basisSignatureDomain))
	mac.Write([]byte{0x1f})
	mac.Write([]byte(keyID))
	mac.Write([]byte{0x1f})
	mac.Write(payload)
	return mac.Sum(nil)
}

func basisAllowsAction(allowed []relmodel.CommandKind, kind relmodel.CommandKind) bool {
	for _, candidate := range allowed {
		if candidate == kind {
			return true
		}
	}
	return false
}
