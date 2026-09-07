// Command release-control exposes the Tag-owned exact Data release candidate query.
package main

import (
	"context"
	"log"
	"os"

	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/tagreleasecontrol"
)

func main() {
	if err := tagreleasecontrol.Run(context.Background(), os.Args[1:]); err != nil {
		log.Fatal(err)
	}
}
