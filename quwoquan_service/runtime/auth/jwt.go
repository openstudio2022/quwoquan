// Package auth 提供轻量 HS256 JWT 的签发与本地验签，用于 access token。
//
// 设计要点（与登录鉴权闭环方案对齐）：
//   - access token = 短期 JWT，服务端本地验签，热路径零存储查询。
//   - claims 唯一真相源：principal(sub/persona)、token_version(ver)、iat/exp、scope。
//   - refresh token 仍为不透明随机串，由各服务的 UserAuth 存储轮换/吊销。
//
// 这里手写 HS256（header.payload.signature），避免引入额外依赖。
package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

var (
	// ErrInvalidToken 表示 token 结构/签名非法。
	ErrInvalidToken = errors.New("AUTH.TOKEN.invalid")
	// ErrExpiredToken 表示 token 已过期。
	ErrExpiredToken = errors.New("AUTH.TOKEN.expired")
)

// Claims 是 access token 的载荷；JSON 字段名保持紧凑。
type Claims struct {
	Subject      string `json:"sub"`           // ownerId / userId
	Persona      string `json:"psn,omitempty"` // 活跃分身 subAccountId
	TokenVersion int    `json:"ver"`           // 吊销用版本号
	Scope        string `json:"scope,omitempty"`
	IssuedAt     int64  `json:"iat"`
	ExpiresAt    int64  `json:"exp"`
}

type jwtHeader struct {
	Alg string `json:"alg"`
	Typ string `json:"typ"`
}

// Signer 用对称密钥签发 access token。
type Signer struct {
	secret []byte
	ttl    time.Duration
	now    func() time.Time
}

// NewHS256Signer 创建签发器；ttl<=0 时回退到 30 分钟。
func NewHS256Signer(secret []byte, ttl time.Duration) *Signer {
	if ttl <= 0 {
		ttl = 30 * time.Minute
	}
	return &Signer{secret: secret, ttl: ttl, now: time.Now}
}

// Sign 生成一个带 sub/persona/ver/scope 的短期 JWT。
func (s *Signer) Sign(subject, persona string, tokenVersion int, scope string) (string, error) {
	if strings.TrimSpace(subject) == "" {
		return "", fmt.Errorf("auth: subject required")
	}
	issued := s.now().UTC()
	claims := Claims{
		Subject:      subject,
		Persona:      persona,
		TokenVersion: tokenVersion,
		Scope:        scope,
		IssuedAt:     issued.Unix(),
		ExpiresAt:    issued.Add(s.ttl).Unix(),
	}
	headerSeg, err := encodeSegment(jwtHeader{Alg: "HS256", Typ: "JWT"})
	if err != nil {
		return "", err
	}
	payloadSeg, err := encodeSegment(claims)
	if err != nil {
		return "", err
	}
	signingInput := headerSeg + "." + payloadSeg
	sig := sign(signingInput, s.secret)
	return signingInput + "." + sig, nil
}

// Verifier 本地验签并解析 claims。
type Verifier struct {
	secret []byte
	now    func() time.Time
}

func NewHS256Verifier(secret []byte) *Verifier {
	return &Verifier{secret: secret, now: time.Now}
}

// Verify 校验签名与过期，返回 claims。
func (v *Verifier) Verify(token string) (*Claims, error) {
	parts := strings.Split(strings.TrimSpace(token), ".")
	if len(parts) != 3 {
		return nil, ErrInvalidToken
	}
	signingInput := parts[0] + "." + parts[1]
	expected := sign(signingInput, v.secret)
	if !hmac.Equal([]byte(expected), []byte(parts[2])) {
		return nil, ErrInvalidToken
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, ErrInvalidToken
	}
	var claims Claims
	if err := json.Unmarshal(payload, &claims); err != nil {
		return nil, ErrInvalidToken
	}
	if claims.ExpiresAt > 0 && v.now().UTC().Unix() >= claims.ExpiresAt {
		return nil, ErrExpiredToken
	}
	if strings.TrimSpace(claims.Subject) == "" {
		return nil, ErrInvalidToken
	}
	return &claims, nil
}

func encodeSegment(v any) (string, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(raw), nil
}

func sign(input string, secret []byte) string {
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(input))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}
