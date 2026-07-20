package accountclosure

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
)

const (
	closedSubjectRedisPrefix = "privacy:closed_subject:"
	openSubjectRedisPrefix   = "privacy:open_subject:"
)

type SubjectDigestor interface {
	DigestSubject(subjectID string) (string, error)
}

type HMACSubjectDigestor struct {
	key []byte
}

func NewHMACSubjectDigestor(secret string) (*HMACSubjectDigestor, error) {
	secret = strings.TrimSpace(secret)
	if len(secret) < 32 {
		return nil, errors.New(
			"account-closure subject HMAC secret must contain at least 32 bytes",
		)
	}
	return &HMACSubjectDigestor{key: []byte(secret)}, nil
}

func (digestor *HMACSubjectDigestor) DigestSubject(
	subjectID string,
) (string, error) {
	subjectID = strings.TrimSpace(subjectID)
	if digestor == nil || len(digestor.key) < 32 {
		return "", errors.New(
			"account-closure subject digestor is not configured",
		)
	}
	if subjectID == "" {
		return "", errors.New("account-closure subject id is required")
	}
	mac := hmac.New(sha256.New, digestor.key)
	_, _ = mac.Write([]byte(subjectID))
	return hex.EncodeToString(mac.Sum(nil)), nil
}

func closedSubjectRedisKey(
	digestor SubjectDigestor,
	subjectID string,
) (string, error) {
	digest, err := digestor.DigestSubject(subjectID)
	if err != nil {
		return "", err
	}
	return closedSubjectRedisPrefix + digest, nil
}

func openSubjectRedisKey(
	digestor SubjectDigestor,
	subjectID string,
) (string, error) {
	digest, err := digestor.DigestSubject(subjectID)
	if err != nil {
		return "", err
	}
	return openSubjectRedisPrefix + digest, nil
}

var _ SubjectDigestor = (*HMACSubjectDigestor)(nil)
