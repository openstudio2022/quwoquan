package reference

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"io"
	"strings"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
)

type Issuer struct {
	random io.Reader
}

func NewIssuer(random io.Reader) *Issuer {
	if random == nil {
		random = rand.Reader
	}
	return &Issuer{random: random}
}

func (issuer *Issuer) Issue(kind string) (string, string, error) {
	if issuer == nil || issuer.random == nil {
		return "", "", fmt.Errorf("opaque reference issuer unavailable")
	}
	kind = strings.TrimSpace(kind)
	if kind == "" {
		return "", "", fmt.Errorf("opaque reference kind is required")
	}
	raw := make([]byte, 32)
	if _, err := io.ReadFull(issuer.random, raw); err != nil {
		return "", "", fmt.Errorf("issue opaque reference: %w", err)
	}
	value := kind + "_" + base64.RawURLEncoding.EncodeToString(raw)
	return value, model.Hash(value), nil
}
