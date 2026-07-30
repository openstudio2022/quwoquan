// Command codegen_chat_domain_events regenerates chat-service domain event
// constants from each messages aggregate's events.yaml contract.
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func main() {
	var metadataDir string
	var outputDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/chat-service/generated/chat", "chat-service generated context directory")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	for _, aggregate := range []string{
		"Conversation",
		"ConversationMembership",
		"ConversationUserState",
		"Message",
	} {
		generator := contractcodegen.NewDomainGenerator(
			source,
			filepath.Join(filepath.Clean(outputDir), contractcodegen.CamelToSnake(aggregate)),
			contractcodegen.WithSliceEntityRefs(),
			contractcodegen.WithObjectFirstRoot(),
		)
		if err := generator.GenerateDomainEvents(aggregate); err != nil {
			exitErr(fmt.Errorf("generate %s events: %w", aggregate, err))
		}
	}
	fmt.Printf("codegen_chat_domain_events: wrote object-local chat event constants under %s\n", outputDir)
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_chat_domain_events error: %v\n", err)
	os.Exit(1)
}
