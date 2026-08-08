package assistant_run_test

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
)

func canonicalFixtureDigest(value any) string {
	payload, err := json.Marshal(value)
	if err != nil {
		panic(err)
	}
	return canonicalContentDigest(payload)
}

func canonicalContentDigest(payload []byte) string {
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:])
}
