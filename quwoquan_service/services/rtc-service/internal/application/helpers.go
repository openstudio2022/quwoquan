package application

import (
	"crypto/rand"
	"encoding/hex"
)

func generateID() string {
	b := make([]byte, 12)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
