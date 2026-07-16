package application

import (
	"fmt"
	"strings"
)

func generateEntityID(generator EntityIDGenerator) (string, error) {
	if generator == nil {
		return "", fmt.Errorf("entity id generator is required")
	}
	id := strings.TrimSpace(generator.NewID())
	if id == "" {
		return "", fmt.Errorf("entity id generator returned an empty id")
	}
	return id, nil
}
