package main

import (
	"fmt"
	"os"

	"quwoquan_provider_protocol_substitute/internal/server"
)

func main() {
	if err := server.RunNativeConformance(os.Stdout); err != nil {
		_, _ = fmt.Fprintln(os.Stderr, "provider_protocol_conformance: GATE_BLOCK:", err)
		os.Exit(2)
	}
}
