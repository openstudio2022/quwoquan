package local_contract

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
)

func canonicalContextFixtureDigest(value any) string {
	payload, err := json.Marshal(value)
	if err != nil {
		panic(err)
	}
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:])
}
