package application

import (
	"strconv"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
)

func FromSearchDocument(document rtsearch.Document, sourceVersion int64) SearchItem {
	return SearchItem{
		CircleID: document.ObjectID, DisplayName: document.Title, Description: document.Summary,
		CoverURL: document.Fields["coverUrl"], CategoryID: document.Fields["categoryId"],
		SubCategory: document.Fields["subCategory"], DomainID: document.Fields["domainId"],
		Kind: document.Fields["kind"], DisplaySubjectType: document.Fields["displaySubjectType"],
		MemberCount:         parseCount(document.Fields["memberCount"]),
		PostCount:           parseCount(document.Fields["postCount"]),
		LinkedHomepageID:    document.Fields["linkedHomepageId"],
		LinkedHomepageType:  document.Fields["linkedHomepageType"],
		LinkedHomepageTitle: document.Fields["linkedHomepageTitle"],
		Visibility:          document.Visibility, Tags: append([]string(nil), document.Tags...),
		SourceVersion: sourceVersion, UpdatedAt: document.Freshness,
	}
}

func parseCount(raw string) int64 {
	value, _ := strconv.ParseInt(strings.TrimSpace(raw), 10, 64)
	return value
}
