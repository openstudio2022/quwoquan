package trust

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"fmt"

	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/readiness"
)

// SignedJourneyCaseAuthority verifies the complete Journey policy before it
// can participate in commercial closure. It never accepts policy from a
// result bundle or runner receipt.
type SignedJourneyCaseAuthority struct {
	catalog    readiness.JourneyCaseCatalog
	sourceHash string
}

func NewSignedJourneyCaseAuthority(
	envelopeBytes []byte,
	keyringBytes []byte,
) (*SignedJourneyCaseAuthority, error) {
	authorities, err := decodeJourneyCatalogKeyring(keyringBytes)
	if err != nil {
		return nil, err
	}
	var envelope SignedCurrentJourneyCatalog
	if err := decodeStrict(envelopeBytes, &envelope, "signed Journey case catalog"); err != nil {
		return nil, err
	}
	if !validIdentity(envelope.KeyID) {
		return nil, fmt.Errorf("signed Journey case catalog identity is invalid")
	}
	publicKey, exists := authorities[envelope.KeyID]
	if !exists {
		return nil, fmt.Errorf("signed Journey case catalog keyId is not trusted")
	}
	payloadBytes, err := base64.StdEncoding.Strict().DecodeString(envelope.Payload)
	if err != nil || len(payloadBytes) == 0 {
		return nil, fmt.Errorf("signed Journey case catalog payload must be non-empty base64")
	}
	signature, err := decodeSignature(envelope.Signature)
	if err != nil {
		return nil, fmt.Errorf("signed Journey case catalog: %w", err)
	}
	if !ed25519.Verify(
		publicKey, JourneyCatalogSigningMessage(payloadBytes), signature,
	) {
		return nil, fmt.Errorf("signed Journey case catalog signature is invalid")
	}
	var payload CurrentJourneyCatalog
	if err := decodeStrict(payloadBytes, &payload, "current Journey case catalog payload"); err != nil {
		return nil, err
	}
	if !isSHA256(payload.ContractGraphSourceHash) ||
		len(payload.Catalog.Journeys) == 0 || len(payload.Catalog.Cases) == 0 {
		return nil, fmt.Errorf("current Journey case catalog identity is invalid")
	}
	return &SignedJourneyCaseAuthority{
		catalog:    deepCopyJourneyCatalog(payload.Catalog),
		sourceHash: payload.ContractGraphSourceHash,
	}, nil
}

func (authority *SignedJourneyCaseAuthority) CurrentJourneyCatalog(
	ctx context.Context,
	current *graph.ContractGraph,
) (readiness.JourneyCaseCatalog, error) {
	if err := ctx.Err(); err != nil {
		return readiness.JourneyCaseCatalog{}, err
	}
	if authority == nil {
		return readiness.JourneyCaseCatalog{}, fmt.Errorf("signed Journey case authority is nil")
	}
	actual, err := readiness.ContractGraphSourceHash(current)
	if err != nil {
		return readiness.JourneyCaseCatalog{}, fmt.Errorf(
			"derive current ContractGraph source hash: %w", err,
		)
	}
	if actual != authority.sourceHash {
		return readiness.JourneyCaseCatalog{}, fmt.Errorf(
			"signed Journey case catalog is stale for ContractGraph source hash",
		)
	}
	return deepCopyJourneyCatalog(authority.catalog), nil
}

func decodeJourneyCatalogKeyring(data []byte) (map[string]ed25519.PublicKey, error) {
	var keyring JourneyCatalogKeyring
	if err := decodeStrict(data, &keyring, "Journey catalog keyring"); err != nil {
		return nil, err
	}
	if len(keyring.Authorities) == 0 {
		return nil, fmt.Errorf("Journey catalog keyring identity is invalid")
	}
	result := make(map[string]ed25519.PublicKey, len(keyring.Authorities))
	for _, authority := range keyring.Authorities {
		if !validIdentity(authority.KeyID) {
			return nil, fmt.Errorf("Journey catalog keyring contains invalid keyId")
		}
		if _, duplicate := result[authority.KeyID]; duplicate {
			return nil, fmt.Errorf(
				"Journey catalog keyring contains duplicate keyId %q", authority.KeyID,
			)
		}
		publicKey, err := decodePublicKey(authority.PublicKey)
		if err != nil {
			return nil, fmt.Errorf(
				"Journey catalog keyring key %q: %w", authority.KeyID, err,
			)
		}
		result[authority.KeyID] = publicKey
	}
	return result, nil
}

func deepCopyJourneyCatalog(value readiness.JourneyCaseCatalog) readiness.JourneyCaseCatalog {
	copy := readiness.JourneyCaseCatalog{
		Journeys: append([]readiness.JourneyDefinition(nil), value.Journeys...),
		Cases:    make([]readiness.JourneyCaseContract, len(value.Cases)),
	}
	for index, item := range value.Cases {
		copy.Cases[index] = item
		copy.Cases[index].Executions = append(
			[]readiness.ExecutionRequirement(nil), item.Executions...,
		)
	}
	return copy
}
