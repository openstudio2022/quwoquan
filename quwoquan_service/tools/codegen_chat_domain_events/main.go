// Command codegen_chat_domain_events regenerates chat-service conversation
// domain event constants from contracts/metadata/messages/conversation/events.yaml.
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"quwoquan_service/runtime/codegen"
	"quwoquan_service/runtime/registry"
)

func main() {
	var metadataDir string
	var outputDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/chat-service/internal", "chat-service internal output directory")
	flag.Parse()

	reg, err := registry.LoadFromDirectory(metadataDir)
	if err != nil {
		exitErr(fmt.Errorf("load registry: %w", err))
	}

	g := codegen.NewGenerator(
		reg,
		filepath.Clean(outputDir),
		codegen.WithTypedEnums(),
		codegen.WithSliceEntityRefs(),
		codegen.WithSkipViewEntities(),
		codegen.WithGoFieldIDSuffix(),
	)
	if err := g.GenerateDomainEventsOnly("Conversation"); err != nil {
		exitErr(fmt.Errorf("generate Conversation events: %w", err))
	}
	fmt.Printf("codegen_chat_domain_events: wrote conversation event constants under %s\n", outputDir)
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_chat_domain_events error: %v\n", err)
	os.Exit(1)
}
