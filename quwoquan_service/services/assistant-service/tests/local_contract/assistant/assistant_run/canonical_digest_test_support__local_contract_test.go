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

func canonicalTravelProjectionFixtureDigest(
	tripID string,
	revisionID string,
	revisionNumber int64,
) string {
	type sourceVersion struct {
		ID      string `json:"id"`
		Version int64  `json:"version"`
	}
	payload := struct {
		TripID         string          `json:"tripId"`
		TripVersion    int64           `json:"tripVersion"`
		TripStatus     string          `json:"tripStatus"`
		RevisionID     string          `json:"revisionId"`
		RevisionNumber int64           `json:"revisionNumber"`
		Moments        []sourceVersion `json:"moments"`
		Links          []sourceVersion `json:"links"`
	}{
		TripID: tripID, TripVersion: 1, TripStatus: "active",
		RevisionID: revisionID, RevisionNumber: revisionNumber,
		Moments: []sourceVersion{}, Links: []sourceVersion{},
	}
	return canonicalFixtureDigest(payload)
}
