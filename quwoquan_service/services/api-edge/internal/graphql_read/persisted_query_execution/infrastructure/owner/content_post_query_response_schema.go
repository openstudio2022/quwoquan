package owner

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
)

type responseValueKind uint8

const (
	responseString responseValueKind = iota + 1
	responseInt
	responseFloat
	responseBool
	responseObject
	responseList
)

type responseValueSpec struct {
	kind     responseValueKind
	nullable bool
	object   *objectSpec
	item     *responseValueSpec
	maxItems int
}

type objectSpec struct {
	fields map[string]responseValueSpec
}

func decodeOwnerGraphQLData(body []byte, binding contentBundleBinding) (map[string]any, error) {
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.UseNumber()
	var envelope map[string]any
	if err := decoder.Decode(&envelope); err != nil {
		return nil, err
	}
	if err := ensureJSONEOF(decoder); err != nil {
		return nil, err
	}
	if len(envelope) != 1 {
		return nil, errors.New("owner GraphQL response must contain only data")
	}
	data, ok := envelope["data"].(map[string]any)
	if !ok || len(data) != 1 {
		return nil, errors.New("owner GraphQL data must contain exactly one root field")
	}
	root, ok := data[binding.rootField].(map[string]any)
	if !ok {
		return nil, fmt.Errorf("owner GraphQL data root %s must be a non-null object", binding.rootField)
	}
	if err := validateObjectResponse(binding.rootField, root, binding.response); err != nil {
		return nil, err
	}
	return root, nil
}

func ensureJSONEOF(decoder *json.Decoder) error {
	var trailing any
	err := decoder.Decode(&trailing)
	if errors.Is(err, io.EOF) {
		return nil
	}
	if err == nil {
		return errors.New("owner GraphQL response contains trailing JSON")
	}
	return err
}

func validateObjectResponse(path string, value map[string]any, spec objectSpec) error {
	if len(value) != len(spec.fields) {
		return fmt.Errorf("%s field set does not match persisted selection", path)
	}
	for name, fieldSpec := range spec.fields {
		field, exists := value[name]
		if !exists {
			return fmt.Errorf("%s.%s is missing", path, name)
		}
		if err := validateResponseValue(path+"."+name, field, fieldSpec); err != nil {
			return err
		}
	}
	return nil
}

func validateResponseValue(path string, value any, spec responseValueSpec) error {
	if value == nil {
		if spec.nullable {
			return nil
		}
		return fmt.Errorf("%s must not be null", path)
	}
	switch spec.kind {
	case responseString:
		if _, ok := value.(string); !ok {
			return fmt.Errorf("%s must be a string", path)
		}
	case responseBool:
		if _, ok := value.(bool); !ok {
			return fmt.Errorf("%s must be a boolean", path)
		}
	case responseInt:
		number, ok := value.(json.Number)
		if !ok {
			return fmt.Errorf("%s must be an integer", path)
		}
		if _, err := number.Int64(); err != nil {
			return fmt.Errorf("%s must be an integer", path)
		}
	case responseFloat:
		number, ok := value.(json.Number)
		if !ok {
			return fmt.Errorf("%s must be a finite number", path)
		}
		parsed, err := number.Float64()
		if err != nil || math.IsInf(parsed, 0) || math.IsNaN(parsed) {
			return fmt.Errorf("%s must be a finite number", path)
		}
	case responseObject:
		object, ok := value.(map[string]any)
		if !ok || spec.object == nil {
			return fmt.Errorf("%s must be an object", path)
		}
		if err := validateObjectResponse(path, object, *spec.object); err != nil {
			return err
		}
	case responseList:
		items, ok := value.([]any)
		if !ok || spec.item == nil {
			return fmt.Errorf("%s must be a list", path)
		}
		if len(items) > spec.maxItems {
			return fmt.Errorf("%s exceeds maximum item count %d", path, spec.maxItems)
		}
		for index, item := range items {
			if err := validateResponseValue(fmt.Sprintf("%s[%d]", path, index), item, *spec.item); err != nil {
				return err
			}
		}
	default:
		return fmt.Errorf("%s has an unsupported response contract", path)
	}
	return nil
}

func baseResponseSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"postId": requiredString(), "contentType": requiredString(),
		"contentIdentity": nullableString(), "assistantUsePolicy": nullableString(),
		"authorId": nullableString(), "authorDisplayName": nullableString(),
		"authorAvatarUrl": nullableString(), "authorAvatarAssetId": nullableString(),
		"authorAvatarAccessMode": nullableString(), "title": nullableString(), "body": nullableString(),
		"summary": nullableString(), "coverUrl": nullableString(),
		"sourceAttribution": nullableObject(sourceAttributionSpec()),
		"location":          nullableObject(geoPointSpec()), "locationName": nullableString(),
		"geoTagRef": nullableString(), "visitedAt": nullableString(),
		"primaryHomepageId": nullableString(), "canonicalEntityId": nullableString(),
		"primaryHomepageType":     nullableString(),
		"primaryHomepageSnapshot": nullableObject(homepageSnapshotSpec()),
		"status":                  requiredString(), "visibility": requiredString(),
		"gatheringRef": nullableString(),
		"likeCount":    requiredInt(), "commentCount": requiredInt(),
		"shareCount": requiredInt(), "viewCount": requiredInt(),
		"viewerLiked": nullableBool(),
		"createdAt":   requiredString(), "updatedAt": requiredString(), "publishedAt": nullableString(),
	})
}

func semanticResponseSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"postId": requiredString(), "contentType": requiredString(),
		"tagRefs":          nullableList(30, requiredString()),
		"entityRefs":       nullableList(30, requiredString()),
		"semanticMentions": nullableList(30, requiredObject(semanticMentionSpec())),
	})
}

func mediaResponseSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"postId": requiredString(), "contentType": requiredString(),
		"mediaAssetIds": nullableList(20, requiredString()),
		"mediaUrls":     nullableList(20, requiredString()),
		"mediaItems":    nullableList(20, requiredObject(mediaItemSpec())),
		"thumbnailUrl":  nullableString(), "videoUrl": nullableString(),
		"width": nullableInt(), "height": nullableInt(), "durationMs": nullableInt(),
		"coverStrategy": nullableString(), "coverFrameTimeMs": nullableInt(),
	})
}

func articleRenderAssetsResponseSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"postId": requiredString(), "contentType": requiredString(),
		"articleMarkdown": nullableString(), "markdownDialect": nullableString(),
		"articleMarkdownDigest":       nullableString(),
		"articleAssetManifestSummary": nullableObject(articleManifestSummarySpec()),
		"articleAssets":               requiredList(20, requiredObject(articleAssetSpec())),
		"articleRenderProfileSummary": nullableObject(articleRenderProfileSpec()),
		"contentVertical":             nullableString(), "articleTemplate": nullableString(),
		"articleFontPreset": nullableString(),
	})
}

func articleEntitiesResponseSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"postId": requiredString(), "contentType": requiredString(),
		"entityMentions": nullableList(30, requiredObject(entityMentionSpec())),
	})
}

func sourceAttributionSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"isOriginal": requiredBool(), "originalCreatorId": nullableString(),
		"originalCreatorName": requiredString(), "originalCreatorProfileUrl": nullableString(),
		"platform": requiredString(), "sourcePostUrl": requiredString(),
		"originalAssetUrl": requiredString(), "attributionText": requiredString(),
		"rightsBasis": requiredString(), "commercialAuthorizationStatus": requiredString(),
		"publicationAdmission": requiredString(), "authorizationProofUrl": nullableString(),
		"termsUrl": nullableString(), "riskAcceptanceId": nullableString(),
		"watermarkStatus": requiredString(), "audioRightsStatus": requiredString(),
		"modelReleaseStatus": requiredString(), "propertyReleaseStatus": requiredString(),
		"collectedAt": requiredString(), "takedownPolicy": requiredString(),
	})
}

func geoPointSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"latitude": requiredFloat(), "longitude": requiredFloat(),
	})
}

func homepageSnapshotSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"canonicalEntityId": nullableString(), "title": nullableString(),
		"subtitle": nullableString(), "coverUrl": nullableString(),
	})
}

func semanticMentionSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"mentionId": requiredString(), "kind": requiredString(), "surface": requiredString(),
		"location": requiredString(), "rangeStart": nullableInt(), "rangeEnd": nullableInt(),
		"status": requiredString(), "candidateId": nullableString(), "targetRef": nullableString(),
	})
}

func mediaItemSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"kind": requiredString(), "mediaAssetId": nullableString(), "mediaAssetVersion": nullableInt(),
		"url": requiredString(), "coverUrl": nullableString(), "durationMs": nullableInt(),
		"width": nullableInt(), "height": nullableInt(), "previewTrackManifestUrl": nullableString(),
		"previewTrackVersion": nullableInt(), "hlsCmafMasterManifestUrl": nullableString(),
		"hlsCmafDescriptorVersion": nullableInt(), "title": nullableString(),
	})
}

func articleManifestSummarySpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"schema": requiredString(), "markdownVersion": nullableString(),
		"markdownDialect": nullableString(), "articleMarkdownDigest": requiredString(),
		"documentSha256": requiredString(), "assetManifestSha256": requiredString(),
		"documentVersionSha256": requiredString(),
	})
}

func articleAssetSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"assetId": requiredString(), "kind": nullableString(), "publicSliceKey": nullableString(),
		"sha256": nullableString(), "mimeType": nullableString(), "sourceOriginalSha256": nullableString(),
		"caption": nullableString(), "role": nullableString(), "width": nullableInt(),
		"height": nullableInt(), "durationMs": nullableInt(), "thumbnailUrl": nullableString(),
		"coverUrl": nullableString(), "coverStrategy": nullableString(),
		"coverFrameTimeMs": nullableInt(), "sourceCollectionId": nullableString(),
	})
}

func articleRenderProfileSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"template": nullableString(), "fontPreset": nullableString(),
		"paperThemeMode": nullableString(), "paperTexture": nullableString(),
	})
}

func entityMentionSpec() objectSpec {
	return exactObject(map[string]responseValueSpec{
		"subjectType": requiredString(), "subjectId": requiredString(),
		"homepageId": requiredString(), "displayName": requiredString(),
		"rangeStart": requiredInt(), "rangeEnd": requiredInt(),
	})
}

func exactObject(fields map[string]responseValueSpec) objectSpec { return objectSpec{fields: fields} }
func requiredString() responseValueSpec                          { return responseValueSpec{kind: responseString} }
func nullableString() responseValueSpec {
	return responseValueSpec{kind: responseString, nullable: true}
}
func requiredInt() responseValueSpec   { return responseValueSpec{kind: responseInt} }
func nullableInt() responseValueSpec   { return responseValueSpec{kind: responseInt, nullable: true} }
func requiredFloat() responseValueSpec { return responseValueSpec{kind: responseFloat} }
func requiredBool() responseValueSpec  { return responseValueSpec{kind: responseBool} }
func nullableBool() responseValueSpec {
	return responseValueSpec{kind: responseBool, nullable: true}
}
func requiredObject(spec objectSpec) responseValueSpec {
	return responseValueSpec{kind: responseObject, object: &spec}
}
func nullableObject(spec objectSpec) responseValueSpec {
	return responseValueSpec{kind: responseObject, nullable: true, object: &spec}
}
func requiredList(maxItems int, item responseValueSpec) responseValueSpec {
	return responseValueSpec{kind: responseList, maxItems: maxItems, item: &item}
}
func nullableList(maxItems int, item responseValueSpec) responseValueSpec {
	return responseValueSpec{kind: responseList, nullable: true, maxItems: maxItems, item: &item}
}
