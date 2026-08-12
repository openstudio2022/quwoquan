package main

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

func sha256Hex(payload []byte) string {
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}

func dartString(value string) string {
	return "'" + strings.NewReplacer("\\", "\\\\", "'", "\\'", "\r", "\\r", "\n", "\\n").Replace(value) + "'"
}
