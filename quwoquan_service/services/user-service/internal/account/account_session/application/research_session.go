package account_session

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/runtime/auth/researchidentity"
)

var (
	ErrResearchIdentityForbidden   = errors.New("research identity is not allowlisted")
	ErrResearchIdentityUnavailable = errors.New("research identity authority is unavailable")
)

// ResearchSessionAuditAppender is the mandatory durable audit boundary for a
// research identity proof. Only irreversible identities may cross this port.
type ResearchSessionAuditAppender interface {
	AppendResearchSessionIssued(
		context.Context,
		ResearchSessionAuditRecord,
	) error
}

type ResearchSessionAuditRecord struct {
	SubjectHash       string
	AttestationIDHash string
	ExpiresAt         time.Time
}

type ResearchSessionResult struct {
	SubjectHash   string    `json:"subjectHash"`
	AttestationID string    `json:"attestationId"`
	ExpiresAt     time.Time `json:"expiresAt"`
}

func NewUnavailableResearchSessionCommandFacade() *ResearchSessionCommandFacade {
	return &ResearchSessionCommandFacade{}
}

// ResearchSessionCommandFacade issues a short-lived, signed proof for an
// already-authenticated and explicitly allowlisted account. It neither creates
// an account nor extends the ordinary AccountSession lifecycle.
type ResearchSessionCommandFacade struct {
	accountAllowlist map[string]struct{}
	authority        *researchidentity.Authority
	ttl              time.Duration
	audit            ResearchSessionAuditAppender
	now              func() time.Time
	random           func([]byte) error
}

func NewResearchSessionCommandFacade(
	accountIDs []string,
	attestationKey []byte,
	ttl time.Duration,
	audit ResearchSessionAuditAppender,
) (*ResearchSessionCommandFacade, error) {
	if ttl <= 0 || ttl > 15*time.Minute {
		return nil, errors.New("research identity TTL must be within 1..900 seconds")
	}
	authority, err := researchidentity.NewAuthority(attestationKey)
	if err != nil {
		return nil, err
	}
	if audit == nil {
		return nil, errors.New("research identity durable audit appender is required")
	}
	allowlist := make(map[string]struct{}, len(accountIDs))
	for _, raw := range accountIDs {
		accountID := strings.TrimSpace(raw)
		if accountID == "" {
			return nil, errors.New("research identity allowlist contains a blank account")
		}
		if _, exists := allowlist[accountID]; exists {
			return nil, errors.New("research identity allowlist contains a duplicate account")
		}
		allowlist[accountID] = struct{}{}
	}
	if len(allowlist) == 0 {
		return nil, errors.New("research identity allowlist must not be empty")
	}
	return &ResearchSessionCommandFacade{
		accountAllowlist: allowlist,
		authority:        authority,
		ttl:              ttl,
		audit:            audit,
		now:              time.Now,
		random: func(value []byte) error {
			_, err := rand.Read(value)
			return err
		},
	}, nil
}

func (facade *ResearchSessionCommandFacade) IssueWhitelistedResearchSession(
	ctx context.Context,
	accountID string,
) (ResearchSessionResult, error) {
	accountID = strings.TrimSpace(accountID)
	if facade == nil || facade.authority == nil || facade.audit == nil {
		return ResearchSessionResult{}, ErrResearchIdentityUnavailable
	}
	if accountID == "" {
		return ResearchSessionResult{}, ErrResearchIdentityForbidden
	}
	if _, allowed := facade.accountAllowlist[accountID]; !allowed {
		return ResearchSessionResult{}, ErrResearchIdentityForbidden
	}
	issuedAt := facade.now().UTC()
	expiresAt := issuedAt.Add(facade.ttl)
	nonce := make([]byte, 32)
	if err := facade.random(nonce); err != nil {
		return ResearchSessionResult{}, fmt.Errorf("%w: attestation nonce: %v", ErrResearchIdentityUnavailable, err)
	}
	verified, attestationID, err := facade.authority.Issue(
		accountID,
		issuedAt,
		expiresAt,
		nonce,
	)
	if err != nil {
		return ResearchSessionResult{}, fmt.Errorf("%w: issue attestation: %v", ErrResearchIdentityUnavailable, err)
	}
	if err := facade.audit.AppendResearchSessionIssued(
		ctx,
		ResearchSessionAuditRecord{
			SubjectHash:       verified.SubjectHash,
			AttestationIDHash: verified.AttestationIDHash,
			ExpiresAt:         expiresAt,
		},
	); err != nil {
		return ResearchSessionResult{}, fmt.Errorf("%w: durable audit append: %v", ErrResearchIdentityUnavailable, err)
	}
	return ResearchSessionResult{
		SubjectHash:   verified.SubjectHash,
		AttestationID: attestationID,
		ExpiresAt:     expiresAt,
	}, nil
}
