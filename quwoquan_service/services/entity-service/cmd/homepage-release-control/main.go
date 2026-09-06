package main

import (
	"context"
	"log"
	"os"

	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/homepageimport"
)

func main() {
	if err := homepageimport.RunHomepageReleaseControl(context.Background(), os.Args[1:]); err != nil {
		log.Fatal(err)
	}
}
