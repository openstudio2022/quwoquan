package application

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtauth "quwoquan_service/runtime/auth"
	rtobs "quwoquan_service/runtime/observability"
	sessionapp "quwoquan_service/services/user-service/internal/application/account/account_session"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/generated"
)

func (s *AuthService) issueLoginResult(
	ctx context.Context,
	ownerID, credType, credKey, deviceID string,
) (*LoginResult, error) {
	if _, err := s.resolvePhysicalShard(ownerID); err != nil {
		return nil, err
	}
	profile, err := s.profiles.FindByID(ctx, ownerID)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("load profile: %v", err))
	}
	if profile != nil && strings.TrimSpace(credType) != credentialAnonymousDevice {
		updated := false
		if strings.TrimSpace(profile.AccountState) == accountStateAnonymous {
			promoteRegisteredProfile(profile)
			updated = true
		}
		if strings.TrimSpace(credType) == credentialPhone && strings.TrimSpace(profile.Phone) == "" {
			profile.Phone = credKey
			updated = true
		}
		if updated {
			if err := s.profiles.Update(ctx, profile); err != nil {
				return nil, generated.AppErrorFromInternalError(fmt.Sprintf("promote owner profile: %v", err))
			}
		}
	}

	activeSub, err := s.personas.FindActiveByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}

	subs, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}

	accessToken, err := s.issueAccessToken(ownerID, activeSub)
	if err != nil {
		return nil, err
	}
	refreshToken, err := generateToken()
	if err != nil {
		return nil, err
	}
	if err := s.openAccountSession(
		ctx,
		ownerID,
		deviceID,
		credType,
		credKey,
		refreshToken,
	); err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("persist refresh token: %v", err))
	}

	return &LoginResult{
		AccessToken:               accessToken,
		RefreshToken:              refreshToken,
		OwnerID:                   ownerID,
		ActiveSub:                 buildActiveSubEnvelope(activeSub),
		SubAccountCount:           len(subs),
		AccountState:              defaultString(profileField(profile, func(p *model.UserProfile) string { return p.AccountState }), accountStateForCredentialType(credType)),
		IdentityOrigin:            defaultString(profileField(profile, func(p *model.UserProfile) string { return p.IdentityOrigin }), identityOriginValue(credType)),
		LogicalShard:              profileIntField(profile, func(p *model.UserProfile) int { return p.LogicalShard }),
		AnonymousRetentionPolicy:  defaultString(profileField(profile, func(p *model.UserProfile) string { return p.AnonymousRetentionPolicy }), anonymousRetentionPolicyForCredentialType(credType)),
		AccountHint:               buildLoginAccountHint(profile, ""),
		SessionRememberTTLSeconds: refreshTokenTTLHours * 60 * 60,
	}, nil
}

// openAccountSession 登录成功后签发新会话：明文 refresh token 只在响应中
// 出现一次，权威状态只保存 SHA-256 哈希与 rotation lineage。
func (s *AuthService) openAccountSession(
	ctx context.Context,
	ownerID, deviceID, credentialType, credentialKey, refreshToken string,
) error {
	if s.sessions == nil {
		return generated.AppErrorFromInternalError(
			"account session command facet unavailable",
		)
	}
	subjectSource := strings.TrimSpace(credentialKey)
	if subjectSource == "" {
		subjectSource = strings.TrimSpace(deviceID)
	}
	subjectDigest := sha256.Sum256([]byte(
		strings.TrimSpace(credentialType) + "\x00" + subjectSource,
	))
	_, err := s.sessions.Issue(
		ctx,
		sessionapp.IssueCommand{
			AccountID:             strings.TrimSpace(ownerID),
			DeviceID:              strings.TrimSpace(deviceID),
			AuthenticationSubject: hex.EncodeToString(subjectDigest[:]),
			IdentityOrigin:        strings.TrimSpace(credentialType),
			RefreshToken:          []byte(refreshToken),
			ExpiresAt: time.Now().UTC().
				Add(refreshTokenTTLHours * time.Hour),
		},
	)
	return err
}

// RefreshToken 单次轮换：旧 hash 标记 rotated 并同 lineage 换发新 token；
// 已轮换 hash 的重放立即吊销整条 lineage。
func (s *AuthService) RefreshToken(ctx context.Context, refreshToken string) (_ *LoginResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.RefreshToken")
	defer func() { rtobs.EndSpan(span, err) }()

	refreshToken = strings.TrimSpace(refreshToken)
	if refreshToken == "" {
		return nil, generated.AppErrorFromInvalidArgument("refreshToken is required")
	}
	if s.sessions == nil {
		return nil, generated.AppErrorFromInternalError(
			"account session command facet unavailable",
		)
	}
	nextToken, err := generateToken()
	if err != nil {
		return nil, err
	}
	issued, err := s.sessions.Rotate(
		ctx,
		sessionapp.RotateCommand{
			CurrentRefreshToken: []byte(refreshToken),
			NextRefreshToken:    []byte(nextToken),
			ExpiresAt: time.Now().UTC().
				Add(refreshTokenTTLHours * time.Hour),
		},
	)
	if err != nil {
		return nil, err
	}

	activeSub, err := s.personas.FindActiveByUserID(ctx, issued.AccountID)
	if err != nil {
		return nil, err
	}
	subs, err := s.personas.FindByUserID(ctx, issued.AccountID)
	if err != nil {
		return nil, err
	}
	profile, err := s.profiles.FindByID(ctx, issued.AccountID)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("load profile: %v", err))
	}
	accessToken, err := s.issueAccessToken(issued.AccountID, activeSub)
	if err != nil {
		return nil, err
	}
	credType := credentialPhone
	if profile != nil && strings.TrimSpace(profile.IdentityOrigin) != "" {
		credType = strings.TrimSpace(profile.IdentityOrigin)
	}
	return &LoginResult{
		AccessToken:               accessToken,
		RefreshToken:              nextToken,
		OwnerID:                   issued.AccountID,
		ActiveSub:                 buildActiveSubEnvelope(activeSub),
		SubAccountCount:           len(subs),
		AccountState:              defaultString(profileField(profile, func(p *model.UserProfile) string { return p.AccountState }), accountStateForCredentialType(credType)),
		IdentityOrigin:            defaultString(profileField(profile, func(p *model.UserProfile) string { return p.IdentityOrigin }), identityOriginValue(credType)),
		LogicalShard:              profileIntField(profile, func(p *model.UserProfile) int { return p.LogicalShard }),
		AnonymousRetentionPolicy:  defaultString(profileField(profile, func(p *model.UserProfile) string { return p.AnonymousRetentionPolicy }), anonymousRetentionPolicyForCredentialType(credType)),
		AccountHint:               buildLoginAccountHint(profile, ""),
		SessionRememberTTLSeconds: refreshTokenTTLHours * 60 * 60,
	}, nil
}

// Logout 吊销 refresh 会话：携带 token 时精确吊销该会话，
// 否则吊销该账号全部会话；对已吊销会话为幂等 no-op。
func (s *AuthService) Logout(ctx context.Context, ownerID, refreshToken string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.Logout",
		attribute.String("owner.id", strings.TrimSpace(ownerID)))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.sessions == nil {
		return generated.AppErrorFromInternalError(
			"account session command facet unavailable",
		)
	}
	refreshToken = strings.TrimSpace(refreshToken)
	if refreshToken != "" {
		return s.sessions.Logout(
			ctx,
			sessionapp.LogoutCommand{RefreshToken: []byte(refreshToken)},
		)
	}
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" {
		return nil
	}
	return s.sessions.Revoke(
		ctx,
		sessionapp.RevokeCommand{AccountID: ownerID, Reason: "logout"},
	)
}

func generateToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(b), nil
}

// issueAccessToken 只签发经统一 trust root 配置的短期 JWT。
func (s *AuthService) issueAccessToken(ownerID string, activeSub *model.Persona) (string, error) {
	if s.accessSigner == nil {
		return "", generated.AppErrorFromInternalError("access token signer unavailable")
	}
	persona := ""
	if activeSub != nil {
		persona = activeSub.SubAccountID
	}
	return s.accessSigner.Sign(rtauth.TokenSubject{
		AccountID: ownerID,
		PersonaID: persona,
	})
}
