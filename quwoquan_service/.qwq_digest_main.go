package main

import (
	"encoding/json"
	"fmt"
	"os"

	releasemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
)

type artifact struct {
	Schema    string               `json:"schema"`
	CommandID string               `json:"commandId"`
	Release   releasemodel.Release `json:"release"`
}

func main() {
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	var a artifact
	if err := json.Unmarshal(raw, &a); err != nil {
		panic(err)
	}
	digest, err := releasemodel.Digest(a.Release)
	if err != nil {
		panic(err)
	}
	fmt.Println(digest)
}
