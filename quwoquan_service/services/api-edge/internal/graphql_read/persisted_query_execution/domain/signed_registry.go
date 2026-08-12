package domain

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
)

const maxSignedRegistryEnvelopeBytes = 16 * 1024 * 1024

type SignatureVerifier interface {
	Verify(ctx context.Context, keyID string, payload, signature []byte) error
}

type signedRegistryEnvelope struct {
	KeyID         string `json:"keyId"`
	PayloadSHA256 string `json:"payloadSha256"`
	Payload       string `json:"payload"`
	Signature     string `json:"signature"`
}

type registryPayload struct {
	CandidateDigest string  `json:"candidateDigest"`
	SchemaDigest    string  `json:"schemaDigest"`
	Entries         []Entry `json:"entries"`
}

func LoadSignedRegistry(
	ctx context.Context,
	reader io.Reader,
	expectedCandidateDigest string,
	expectedSchemaDigest string,
	verifier SignatureVerifier,
) (*Registry, error) {
	if reader == nil {
		return nil, errors.New("signed registry reader is required")
	}
	if verifier == nil {
		return nil, errors.New("signed registry verifier is required")
	}
	if !ValidDigest(expectedCandidateDigest) {
		return nil, errors.New("expected candidate digest must be canonical sha256")
	}
	if !ValidDigest(expectedSchemaDigest) {
		return nil, errors.New("expected schema digest must be canonical sha256")
	}

	limited := io.LimitReader(reader, maxSignedRegistryEnvelopeBytes+1)
	encoded, err := io.ReadAll(limited)
	if err != nil {
		return nil, fmt.Errorf("read signed registry envelope: %w", err)
	}
	if len(encoded) > maxSignedRegistryEnvelopeBytes {
		return nil, errors.New("signed registry envelope exceeds size limit")
	}
	var envelope signedRegistryEnvelope
	if err := decodeStrictJSON(encoded, &envelope); err != nil {
		return nil, fmt.Errorf("decode signed registry envelope: %w", err)
	}
	if envelope.KeyID == "" {
		return nil, errors.New("signed registry keyId is required")
	}
	if !ValidDigest(envelope.PayloadSHA256) {
		return nil, errors.New("signed registry payloadSha256 must be canonical")
	}
	payloadBytes, err := base64.StdEncoding.Strict().DecodeString(envelope.Payload)
	if err != nil {
		return nil, fmt.Errorf("decode signed registry payload: %w", err)
	}
	signatureBytes, err := base64.StdEncoding.Strict().DecodeString(envelope.Signature)
	if err != nil {
		return nil, fmt.Errorf("decode signed registry signature: %w", err)
	}
	if len(signatureBytes) == 0 {
		return nil, errors.New("signed registry signature is required")
	}
	payloadSum := sha256.Sum256(payloadBytes)
	payloadDigest := "sha256:" + hex.EncodeToString(payloadSum[:])
	if payloadDigest != envelope.PayloadSHA256 {
		return nil, errors.New("signed registry payload digest mismatch")
	}
	if err := verifier.Verify(ctx, envelope.KeyID, payloadBytes, signatureBytes); err != nil {
		return nil, fmt.Errorf("verify signed registry: %w", err)
	}

	var payload registryPayload
	if err := decodeStrictJSON(payloadBytes, &payload); err != nil {
		return nil, fmt.Errorf("decode verified registry payload: %w", err)
	}
	if payload.CandidateDigest != expectedCandidateDigest {
		return nil, errors.New("verified registry candidate digest does not match deployment candidate")
	}
	if payload.SchemaDigest != expectedSchemaDigest {
		return nil, errors.New("verified registry schema digest does not match deployed schema")
	}
	return newRegistry(payload.Entries, RegistrySource{
		Kind:            RegistrySourceSigned,
		CandidateDigest: payload.CandidateDigest,
		SchemaDigest:    payload.SchemaDigest,
		SignatureKeyID:  envelope.KeyID,
		PayloadDigest:   payloadDigest,
	})
}

func decodeStrictJSON(payload []byte, destination any) error {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return err
	}
	if decoder.More() {
		return errors.New("multiple JSON values are forbidden")
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("multiple JSON values are forbidden")
		}
		return err
	}
	return nil
}
