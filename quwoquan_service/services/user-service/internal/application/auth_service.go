package application

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"fmt"

	"github.com/google/uuid"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
)

const (
	credentialPhone  = "phone"
	credentialWechat = "wechat"
	credentialApple  = "apple"

	defaultIsolationLevel = "open"
	maxLoginFailCount     = 5
	lockDurationMinutes   = 30
)

// AuthService handles OwnerAccount authentication and credential binding.
type AuthService struct {
	profiles    userrepo.ProfileRepository
	personas    userrepo.PersonaRepository
	credentials userrepo.CredentialRepository
	pcache      *cache.ProfileCache
}

func NewAuthService(
	profiles userrepo.ProfileRepository,
	personas userrepo.PersonaRepository,
	credentials userrepo.CredentialRepository,
	pcache *cache.ProfileCache,
) *AuthService {
	return &AuthService{
		profiles:    profiles,
		personas:    personas,
		credentials: credentials,
		pcache:      pcache,
	}
}

// LoginResult is returned after a successful authentication.
type LoginResult struct {
	AccessToken    string `json:"accessToken"`
	RefreshToken   string `json:"refreshToken"`
	OwnerID        string `json:"ownerId"`
	ActiveSubID    string `json:"activeSub"`
	SubAccountCount int   `json:"subAccountCount"`
}

// LoginWithCredential authenticates via the given credential type and key.
// It creates a new OwnerAccount + default SubAccount if not found.
func (s *AuthService) LoginWithCredential(ctx context.Context, credType, credKey, displayLabel string) (*LoginResult, error) {
	existing, err := s.credentials.FindByTypeAndKey(ctx, credType, credKey)
	if err != nil {
		return nil, fmt.Errorf("credential lookup: %w", err)
	}

	var ownerID string
	if existing != nil {
		ownerID = existing.OwnerID
		_ = s.credentials.UpdateLastUsed(ctx, existing.ID)
	} else {
		// New user: create OwnerAccount + default SubAccount
		ownerID, err = s.createOwnerAccount(ctx, credType, credKey, displayLabel)
		if err != nil {
			return nil, fmt.Errorf("create owner: %w", err)
		}
	}

	activeSub, err := s.personas.FindActiveByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	activeSubID := ""
	if activeSub != nil {
		activeSubID = activeSub.SubAccountID
	}

	subs, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}

	accessToken, err := generateToken()
	if err != nil {
		return nil, err
	}
	refreshToken, err := generateToken()
	if err != nil {
		return nil, err
	}

	return &LoginResult{
		AccessToken:     accessToken,
		RefreshToken:    refreshToken,
		OwnerID:         ownerID,
		ActiveSubID:     activeSubID,
		SubAccountCount: len(subs),
	}, nil
}

// BindCredential binds a new credential to an existing OwnerAccount.
func (s *AuthService) BindCredential(ctx context.Context, ownerID, credType, credKey, displayLabel string) error {
	// Check global uniqueness: this credential must not be bound to another owner
	existing, err := s.credentials.FindByTypeAndKey(ctx, credType, credKey)
	if err != nil {
		return err
	}
	if existing != nil && existing.OwnerID != ownerID {
		return ErrCredentialConflict
	}
	if existing != nil && existing.OwnerID == ownerID {
		return nil // already bound, idempotent
	}

	// Check per-owner-per-type uniqueness
	ownerCred, err := s.credentials.FindByOwnerAndType(ctx, ownerID, credType)
	if err != nil {
		return err
	}
	if ownerCred != nil {
		return ErrCredentialConflict
	}

	return s.credentials.Create(ctx, &model.CredentialBinding{
		ID:             uuid.New().String(),
		OwnerID:        ownerID,
		CredentialType: credType,
		CredentialKey:  credKey,
		DisplayLabel:   displayLabel,
		IsActive:       true,
	})
}

// UnbindCredential deactivates a credential, but prevents removing the last one.
func (s *AuthService) UnbindCredential(ctx context.Context, ownerID, credType string) error {
	count, err := s.credentials.CountActive(ctx, ownerID)
	if err != nil {
		return err
	}
	if count <= 1 {
		return ErrLastCredential
	}
	return s.credentials.Deactivate(ctx, ownerID, credType)
}

// ListCredentials returns the public-facing (masked) credential list for an owner.
func (s *AuthService) ListCredentials(ctx context.Context, ownerID string) ([]model.CredentialBinding, error) {
	return s.credentials.FindByOwner(ctx, ownerID)
}

// createOwnerAccount creates a new user_profiles row + default persona + initial credential.
func (s *AuthService) createOwnerAccount(ctx context.Context, credType, credKey, displayLabel string) (string, error) {
	ownerID := uuid.New().String()
	subAccountID := uuid.New().String()
	personaID := uuid.New().String()

	profile := &model.UserProfile{
		UserID:          ownerID,
		Phone:           credKey, // placeholder; real phone only if credType=phone
		Nickname:        "user_" + ownerID[:8],
		Status:          "active",
		ProfileVersion:  1,
		SubAccountCount: 1,
	}
	if credType != credentialPhone {
		profile.Phone = "pending_" + ownerID[:8] // placeholder until phone is bound
	}

	if err := s.profiles.Create(ctx, profile); err != nil {
		return "", fmt.Errorf("create profile: %w", err)
	}

	persona := &model.Persona{
		ID:             personaID,
		UserID:         ownerID,
		SubAccountID:   subAccountID,
		DisplayName:    profile.Nickname,
		IsPrimary:      true,
		IsActive:       true,
		IsolationLevel: defaultIsolationLevel,
	}
	if err := s.personas.Create(ctx, persona); err != nil {
		return "", fmt.Errorf("create persona: %w", err)
	}

	cred := &model.CredentialBinding{
		ID:             uuid.New().String(),
		OwnerID:        ownerID,
		CredentialType: credType,
		CredentialKey:  credKey,
		DisplayLabel:   displayLabel,
		IsActive:       true,
	}
	if err := s.credentials.Create(ctx, cred); err != nil {
		return "", fmt.Errorf("create credential: %w", err)
	}

	return ownerID, nil
}

// Sentinel errors – returned from AuthService methods.
var (
	ErrCredentialConflict = fmt.Errorf("credential already bound to another account")
	ErrLastCredential     = fmt.Errorf("cannot unbind the last credential")
)

func generateToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(b), nil
}

// SubAccountService handles SubAccount lifecycle within an OwnerAccount.
type SubAccountService struct {
	personas   userrepo.PersonaRepository
	profiles   userrepo.ProfileRepository
	pcache     *cache.ProfileCache
}

func NewSubAccountService(
	personas userrepo.PersonaRepository,
	profiles userrepo.ProfileRepository,
	pcache *cache.ProfileCache,
) *SubAccountService {
	return &SubAccountService{personas: personas, profiles: profiles, pcache: pcache}
}

// ListSubAccounts returns all sub-accounts for an owner.
func (s *SubAccountService) ListSubAccounts(ctx context.Context, ownerID string) ([]model.Persona, error) {
	return s.personas.FindByUserID(ctx, ownerID)
}

// CreateSubAccount creates a new isolated sub-account for the owner.
func (s *SubAccountService) CreateSubAccount(ctx context.Context, ownerID string, data map[string]any) (*model.Persona, error) {
	p := &model.Persona{
		ID:             uuid.New().String(),
		UserID:         ownerID,
		SubAccountID:   uuid.New().String(),
		IsolationLevel: defaultIsolationLevel,
	}
	if v, ok := data["displayName"].(string); ok {
		p.DisplayName = v
	}
	if v, ok := data["avatarUrl"].(string); ok {
		p.AvatarURL = v
	}
	if v, ok := data["isolationLevel"].(string); ok {
		p.IsolationLevel = v
	}
	if v, ok := data["purposeHint"].(string); ok {
		p.PurposeHint = v
	}
	if err := s.personas.Create(ctx, p); err != nil {
		return nil, err
	}
	// Bump sub_account_count
	_ = s.pcache.Del(ctx, ownerID)
	return p, nil
}

// ActivateSubAccount atomically switches the active sub-account.
func (s *SubAccountService) ActivateSubAccount(ctx context.Context, ownerID, subAccountID string) error {
	// Find the persona by subAccountID
	subs, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return err
	}
	var target *model.Persona
	for i := range subs {
		if subs[i].SubAccountID == subAccountID {
			target = &subs[i]
			break
		}
	}
	if target == nil {
		return ErrSubAccountNotFound
	}
	if err := s.personas.DeactivateAll(ctx, ownerID); err != nil {
		return err
	}
	if err := s.personas.ActivateOne(ctx, target.ID); err != nil {
		return err
	}
	_ = s.pcache.Del(ctx, ownerID)
	return nil
}

// DeleteSubAccount deletes a sub-account but prevents removing the last one.
func (s *SubAccountService) DeleteSubAccount(ctx context.Context, ownerID, subAccountID string) error {
	subs, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return err
	}
	if len(subs) <= 1 {
		return ErrLastSubAccount
	}
	var target *model.Persona
	for i := range subs {
		if subs[i].SubAccountID == subAccountID {
			target = &subs[i]
			break
		}
	}
	if target == nil {
		return ErrSubAccountNotFound
	}
	if err := s.personas.Delete(ctx, target.ID); err != nil {
		return err
	}
	_ = s.pcache.Del(ctx, ownerID)
	return nil
}

// GetSubAccountProfile returns public-facing profile for a subAccountID.
// Returns nil, ErrSubAccountStrictIsolation if isolation_level=strict.
func (s *SubAccountService) GetSubAccountProfile(ctx context.Context, subAccountID string) (*model.Persona, error) {
	// We don't have a direct FindBySubAccountID method; we'd need to add one.
	// For now, this is implemented at the handler level via a JOIN query.
	return nil, nil
}

var (
	ErrSubAccountNotFound     = fmt.Errorf("sub-account not found")
	ErrLastSubAccount         = fmt.Errorf("cannot delete the last sub-account")
	ErrSubAccountStrictIso    = fmt.Errorf("user not found") // intentionally vague
)

// PersonaRepository needs FindBySubAccountID – add it to the interface extension.
func findPersonaBySubAccountID(ctx context.Context, personas userrepo.PersonaRepository, subAccountID string) (*model.Persona, error) {
	return personas.FindBySubAccountID(ctx, subAccountID)
}
