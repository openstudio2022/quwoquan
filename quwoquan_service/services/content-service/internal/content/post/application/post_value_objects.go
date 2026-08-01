package post

import (
	"encoding/json"
	"fmt"
	"strings"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
)

// DecodeSubmitPostPublicationContent turns the generated publication command
// payload into the Post aggregate while preserving strict nested value-object
// validation. encoding/json alone silently drops unknown nested fields, which
// would allow client-owned storage authority to bypass the contract boundary.
func DecodeSubmitPostPublicationContent(payload map[string]any) (postmodel.Post, error) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return postmodel.Post{}, err
	}
	var content postmodel.Post
	if err := json.Unmarshal(encoded, &content); err != nil {
		return postmodel.Post{}, err
	}
	if raw, exists := payload["semanticMentions"]; exists {
		content.SemanticMentions, err = decodePostSemanticMentions(raw)
		if err != nil {
			return postmodel.Post{}, err
		}
	}
	if raw, exists := payload["articleAssetManifest"]; exists {
		content.ArticleAssetManifest, err = decodePostArticleAssetManifest(raw)
		if err != nil {
			return postmodel.Post{}, err
		}
	}
	if raw, exists := payload["articleRenderProfile"]; exists {
		content.ArticleRenderProfile, err = decodePostArticleRenderProfile(raw)
		if err != nil {
			return postmodel.Post{}, err
		}
	}
	if raw, exists := payload["primaryHomepageSnapshot"]; exists {
		content.PrimaryHomepageSnapshot, err = decodePostHomepageSnapshot(raw)
		if err != nil {
			return postmodel.Post{}, err
		}
	}
	return content, nil
}

func decodePostSemanticMentions(raw any) ([]postmodel.PostSemanticMention, error) {
	if raw == nil {
		return nil, nil
	}
	if typed, ok := raw.([]postmodel.PostSemanticMention); ok {
		return append([]postmodel.PostSemanticMention(nil), typed...), nil
	}
	rows, err := objectRows(raw, "semanticMentions")
	if err != nil {
		return nil, err
	}
	mentions := make([]postmodel.PostSemanticMention, 0, len(rows))
	for index, row := range rows {
		if err := rejectUnknownFields(row, fieldSet(
			"mentionId", "kind", "surface", "location", "rangeStart", "rangeEnd",
			"status", "candidateId", "targetRef",
		)); err != nil {
			return nil, fmt.Errorf("semanticMentions[%d]: %w", index, err)
		}
		mentions = append(mentions, postmodel.PostSemanticMention{
			MentionId:   strings.TrimSpace(asString(row["mentionId"])),
			Kind:        strings.TrimSpace(asString(row["kind"])),
			Surface:     strings.TrimSpace(asString(row["surface"])),
			Location:    strings.TrimSpace(asString(row["location"])),
			RangeStart:  asInt64Flexible(row["rangeStart"]),
			RangeEnd:    asInt64Flexible(row["rangeEnd"]),
			Status:      strings.TrimSpace(asString(row["status"])),
			CandidateId: strings.TrimSpace(asString(row["candidateId"])),
			TargetRef:   strings.TrimSpace(asString(row["targetRef"])),
		})
	}
	return mentions, nil
}

func decodePostMediaItems(raw any) ([]postmodel.PostMediaItem, error) {
	if raw == nil {
		return nil, nil
	}
	if typed, ok := raw.([]postmodel.PostMediaItem); ok {
		return append([]postmodel.PostMediaItem(nil), typed...), nil
	}
	rows, err := objectRows(raw, "mediaItems")
	if err != nil {
		return nil, err
	}
	items := make([]postmodel.PostMediaItem, 0, len(rows))
	for index, row := range rows {
		if err := rejectUnknownFields(row, fieldSet(
			"kind", "mediaAssetId", "mediaAssetVersion", "url", "coverUrl",
			"thumbnailUrl", "durationMs", "width", "height",
			"previewTrackManifestUrl", "previewTrackVersion",
			"hlsCmafMasterManifestUrl", "hlsCmafDescriptorVersion", "title",
			"coverStrategy", "coverFrameTimeMs",
		)); err != nil {
			return nil, fmt.Errorf("mediaItems[%d]: %w", index, err)
		}
		items = append(items, postmodel.PostMediaItem{
			Kind:                     strings.TrimSpace(asString(row["kind"])),
			MediaAssetId:             strings.TrimSpace(asString(row["mediaAssetId"])),
			MediaAssetVersion:        asInt64Flexible(row["mediaAssetVersion"]),
			Url:                      strings.TrimSpace(asString(row["url"])),
			CoverUrl:                 strings.TrimSpace(asString(row["coverUrl"])),
			ThumbnailUrl:             strings.TrimSpace(asString(row["thumbnailUrl"])),
			DurationMs:               asInt64Flexible(row["durationMs"]),
			Width:                    asInt64Flexible(row["width"]),
			Height:                   asInt64Flexible(row["height"]),
			PreviewTrackManifestUrl:  strings.TrimSpace(asString(row["previewTrackManifestUrl"])),
			PreviewTrackVersion:      asInt64Flexible(row["previewTrackVersion"]),
			HlsCmafMasterManifestUrl: strings.TrimSpace(asString(row["hlsCmafMasterManifestUrl"])),
			HlsCmafDescriptorVersion: asInt64Flexible(row["hlsCmafDescriptorVersion"]),
			Title:                    strings.TrimSpace(asString(row["title"])),
			CoverStrategy:            strings.TrimSpace(asString(row["coverStrategy"])),
			CoverFrameTimeMs:         asInt64Flexible(row["coverFrameTimeMs"]),
		})
	}
	return items, nil
}

func decodePostArticleAssetManifest(raw any) (postmodel.PostArticleAssetManifest, error) {
	if raw == nil {
		return postmodel.PostArticleAssetManifest{}, nil
	}
	row, err := objectRow(raw, "articleAssetManifest")
	if err != nil {
		return postmodel.PostArticleAssetManifest{}, err
	}
	if err := rejectUnknownFields(row, fieldSet(
		"schema", "markdownVersion", "assets",
	)); err != nil {
		return postmodel.PostArticleAssetManifest{}, err
	}
	assetRows, err := objectRows(row["assets"], "articleAssetManifest.assets")
	if err != nil {
		return postmodel.PostArticleAssetManifest{}, err
	}
	assets := make([]postmodel.PostArticleAsset, 0, len(assetRows))
	for index, asset := range assetRows {
		if err := rejectUnknownFields(asset, fieldSet(
			"assetId", "caption", "role", "layout",
		)); err != nil {
			return postmodel.PostArticleAssetManifest{}, fmt.Errorf("articleAssetManifest.assets[%d]: %w", index, err)
		}
		assets = append(assets, postmodel.PostArticleAsset{
			AssetId: strings.TrimSpace(asString(asset["assetId"])),
			Caption: strings.TrimSpace(asString(asset["caption"])),
			Role:    strings.TrimSpace(asString(asset["role"])),
			Layout:  strings.TrimSpace(asString(asset["layout"])),
		})
	}
	return postmodel.PostArticleAssetManifest{
		Schema:          strings.TrimSpace(asString(row["schema"])),
		MarkdownVersion: strings.TrimSpace(asString(row["markdownVersion"])),
		Assets:          assets,
	}, nil
}

func decodePostArticleRenderProfile(raw any) (postmodel.PostArticleRenderProfile, error) {
	if raw == nil {
		return postmodel.PostArticleRenderProfile{}, nil
	}
	if typed, ok := raw.(postmodel.PostArticleRenderProfile); ok {
		return typed, nil
	}
	row, err := objectRow(raw, "articleRenderProfile")
	if err != nil {
		return postmodel.PostArticleRenderProfile{}, err
	}
	if err := rejectUnknownFields(row, fieldSet(
		"template", "fontPreset", "paperThemeMode", "paperTexture", "contentVertical",
		"layoutPolicy", "width", "height", "durationMs",
	)); err != nil {
		return postmodel.PostArticleRenderProfile{}, err
	}
	layout, err := decodePostArticleLayoutPolicy(row["layoutPolicy"])
	if err != nil {
		return postmodel.PostArticleRenderProfile{}, err
	}
	return postmodel.PostArticleRenderProfile{
		Template:        strings.TrimSpace(asString(row["template"])),
		FontPreset:      strings.TrimSpace(asString(row["fontPreset"])),
		PaperThemeMode:  strings.TrimSpace(asString(row["paperThemeMode"])),
		PaperTexture:    strings.TrimSpace(asString(row["paperTexture"])),
		ContentVertical: strings.TrimSpace(asString(row["contentVertical"])),
		LayoutPolicy:    layout,
		Width:           asInt64Flexible(row["width"]),
		Height:          asInt64Flexible(row["height"]),
		DurationMs:      asInt64Flexible(row["durationMs"]),
	}, nil
}

func decodePostArticleLayoutPolicy(raw any) (postmodel.PostArticleLayoutPolicy, error) {
	if raw == nil {
		return postmodel.PostArticleLayoutPolicy{}, nil
	}
	if typed, ok := raw.(postmodel.PostArticleLayoutPolicy); ok {
		return typed, nil
	}
	row, err := objectRow(raw, "articleRenderProfile.layoutPolicy")
	if err != nil {
		return postmodel.PostArticleLayoutPolicy{}, err
	}
	if err := rejectUnknownFields(row, fieldSet("wrapDowngrade", "galleryDowngrade")); err != nil {
		return postmodel.PostArticleLayoutPolicy{}, err
	}
	return postmodel.PostArticleLayoutPolicy{
		WrapDowngrade:    strings.TrimSpace(asString(row["wrapDowngrade"])),
		GalleryDowngrade: strings.TrimSpace(asString(row["galleryDowngrade"])),
	}, nil
}

func decodePostHomepageSnapshot(raw any) (postmodel.PostHomepageSnapshot, error) {
	if raw == nil {
		return postmodel.PostHomepageSnapshot{}, nil
	}
	if typed, ok := raw.(postmodel.PostHomepageSnapshot); ok {
		return typed, nil
	}
	row, err := objectRow(raw, "primaryHomepageSnapshot")
	if err != nil {
		return postmodel.PostHomepageSnapshot{}, err
	}
	if err := rejectUnknownFields(row, fieldSet(
		"canonicalEntityId", "title", "subtitle", "coverUrl", "width", "height", "durationMs",
	)); err != nil {
		return postmodel.PostHomepageSnapshot{}, err
	}
	return postmodel.PostHomepageSnapshot{
		CanonicalEntityId: strings.TrimSpace(asString(row["canonicalEntityId"])),
		Title:             strings.TrimSpace(asString(row["title"])),
		Subtitle:          strings.TrimSpace(asString(row["subtitle"])),
		CoverUrl:          strings.TrimSpace(asString(row["coverUrl"])),
		Width:             asInt64Flexible(row["width"]),
		Height:            asInt64Flexible(row["height"]),
		DurationMs:        asInt64Flexible(row["durationMs"]),
	}, nil
}

func objectRow(raw any, field string) (map[string]any, error) {
	row, ok := raw.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("%s must be an object", field)
	}
	return row, nil
}

func objectRows(raw any, field string) ([]map[string]any, error) {
	if raw == nil {
		return nil, nil
	}
	if typed, ok := raw.([]map[string]any); ok {
		return typed, nil
	}
	values, ok := raw.([]any)
	if !ok {
		return nil, fmt.Errorf("%s must be an object array", field)
	}
	rows := make([]map[string]any, 0, len(values))
	for index, value := range values {
		row, ok := value.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("%s[%d] must be an object", field, index)
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func fieldSet(fields ...string) map[string]struct{} {
	set := make(map[string]struct{}, len(fields))
	for _, field := range fields {
		set[field] = struct{}{}
	}
	return set
}

func rejectUnknownFields(row map[string]any, allowed map[string]struct{}) error {
	for field := range row {
		if _, found := allowed[field]; !found {
			return fmt.Errorf("unknown field %q", field)
		}
	}
	return nil
}
