// Code generated from canonical request_bindings and typed fields. DO NOT EDIT.
package transport

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"unicode/utf8"
)

var _ = utf8.RuneCountInString

type GeneratedGetFeedClientPresentationContractQuery struct {
	ContentTypes        []string `json:"contentTypes"`
	ContractDigest      string   `json:"contractDigest"`
	ListObjectKinds     []string `json:"listObjectKinds"`
	OpenSurfaces        []string `json:"openSurfaces"`
	PresentationRecipes []string `json:"presentationRecipes"`
}

func validateGeneratedGetFeedClientPresentationContractQuery(raw any) error {
	value, ok := raw.(map[string]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	for key := range value {
		switch key {
		case "contentTypes", "contractDigest", "listObjectKinds", "openSurfaces", "presentationRecipes":
		default:
			return fmt.Errorf("invalid typed JSON query field")
		}
	}
	if _, ok := value["contentTypes"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["listObjectKinds"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["presentationRecipes"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["openSurfaces"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["contractDigest"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if field, ok := value["contentTypes"]; ok {
		if err := validateGeneratedGetFeedClientPresentationContractQueryContentTypes(field); err != nil {
			return err
		}
	}
	if field, ok := value["contractDigest"]; ok {
		if err := validateGeneratedGetFeedClientPresentationContractQueryContractDigest(field); err != nil {
			return err
		}
	}
	if field, ok := value["listObjectKinds"]; ok {
		if err := validateGeneratedGetFeedClientPresentationContractQueryListObjectKinds(field); err != nil {
			return err
		}
	}
	if field, ok := value["openSurfaces"]; ok {
		if err := validateGeneratedGetFeedClientPresentationContractQueryOpenSurfaces(field); err != nil {
			return err
		}
	}
	if field, ok := value["presentationRecipes"]; ok {
		if err := validateGeneratedGetFeedClientPresentationContractQueryPresentationRecipes(field); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetFeedClientPresentationContractQueryContentTypes(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedGetFeedClientPresentationContractQueryContentTypesItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetFeedClientPresentationContractQueryContentTypesItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "image", "video", "article":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedGetFeedClientPresentationContractQueryContractDigest(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	if utf8.RuneCountInString(value) < 71 {
		return fmt.Errorf("JSON query below minimum")
	}
	if utf8.RuneCountInString(value) > 71 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	if matched, err := regexp.MatchString("^sha256:[0-9a-f]{64}$", value); err != nil || !matched {
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedGetFeedClientPresentationContractQueryListObjectKinds(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedGetFeedClientPresentationContractQueryListObjectKindsItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetFeedClientPresentationContractQueryListObjectKindsItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "post", "entity_homepage":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedGetFeedClientPresentationContractQueryOpenSurfaces(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedGetFeedClientPresentationContractQueryOpenSurfacesItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetFeedClientPresentationContractQueryOpenSurfacesItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "home_feed", "profile_works", "media_immersive", "article_reader", "homepage_detail":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedGetFeedClientPresentationContractQueryPresentationRecipes(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedGetFeedClientPresentationContractQueryPresentationRecipesItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetFeedClientPresentationContractQueryPresentationRecipesItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "cover_media_card", "article_excerpt_card", "homepage_summary_card":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func BindGeneratedGetFeedClientPresentationContractQuery(r *http.Request) (*GeneratedGetFeedClientPresentationContractQuery, error) {
	values, err := url.ParseQuery(r.URL.RawQuery)
	if err != nil {
		return nil, fmt.Errorf("invalid query encoding")
	}
	entries, present := values["clientPresentationContract"]
	if !present {
		return nil, nil
	}
	if len(entries) != 1 || strings.TrimSpace(entries[0]) == "" || len(entries[0]) > 8192 || !utf8.ValidString(entries[0]) {
		return nil, fmt.Errorf("invalid JSON query cardinality or byte length")
	}
	decoder := json.NewDecoder(strings.NewReader(entries[0]))
	decoder.UseNumber()
	var raw any
	if err := decoder.Decode(&raw); err != nil {
		return nil, fmt.Errorf("invalid JSON query object")
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		return nil, fmt.Errorf("JSON query contains trailing data")
	}
	if raw == nil {
		return nil, fmt.Errorf("JSON query must be an object")
	}
	if err := validateGeneratedGetFeedClientPresentationContractQuery(raw); err != nil {
		return nil, err
	}
	var value GeneratedGetFeedClientPresentationContractQuery
	if err := json.Unmarshal([]byte(entries[0]), &value); err != nil {
		return nil, fmt.Errorf("invalid typed JSON query")
	}
	return &value, nil
}

type GeneratedListUserPostsClientPresentationContractQuery struct {
	ContentTypes        []string `json:"contentTypes"`
	ContractDigest      string   `json:"contractDigest"`
	ListObjectKinds     []string `json:"listObjectKinds"`
	OpenSurfaces        []string `json:"openSurfaces"`
	PresentationRecipes []string `json:"presentationRecipes"`
}

func validateGeneratedListUserPostsClientPresentationContractQuery(raw any) error {
	value, ok := raw.(map[string]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	for key := range value {
		switch key {
		case "contentTypes", "contractDigest", "listObjectKinds", "openSurfaces", "presentationRecipes":
		default:
			return fmt.Errorf("invalid typed JSON query field")
		}
	}
	if _, ok := value["contentTypes"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["listObjectKinds"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["presentationRecipes"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["openSurfaces"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["contractDigest"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if field, ok := value["contentTypes"]; ok {
		if err := validateGeneratedListUserPostsClientPresentationContractQueryContentTypes(field); err != nil {
			return err
		}
	}
	if field, ok := value["contractDigest"]; ok {
		if err := validateGeneratedListUserPostsClientPresentationContractQueryContractDigest(field); err != nil {
			return err
		}
	}
	if field, ok := value["listObjectKinds"]; ok {
		if err := validateGeneratedListUserPostsClientPresentationContractQueryListObjectKinds(field); err != nil {
			return err
		}
	}
	if field, ok := value["openSurfaces"]; ok {
		if err := validateGeneratedListUserPostsClientPresentationContractQueryOpenSurfaces(field); err != nil {
			return err
		}
	}
	if field, ok := value["presentationRecipes"]; ok {
		if err := validateGeneratedListUserPostsClientPresentationContractQueryPresentationRecipes(field); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedListUserPostsClientPresentationContractQueryContentTypes(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedListUserPostsClientPresentationContractQueryContentTypesItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedListUserPostsClientPresentationContractQueryContentTypesItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "image", "video", "article":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedListUserPostsClientPresentationContractQueryContractDigest(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	if utf8.RuneCountInString(value) < 71 {
		return fmt.Errorf("JSON query below minimum")
	}
	if utf8.RuneCountInString(value) > 71 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	if matched, err := regexp.MatchString("^sha256:[0-9a-f]{64}$", value); err != nil || !matched {
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedListUserPostsClientPresentationContractQueryListObjectKinds(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedListUserPostsClientPresentationContractQueryListObjectKindsItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedListUserPostsClientPresentationContractQueryListObjectKindsItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "post", "entity_homepage":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedListUserPostsClientPresentationContractQueryOpenSurfaces(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedListUserPostsClientPresentationContractQueryOpenSurfacesItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedListUserPostsClientPresentationContractQueryOpenSurfacesItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "home_feed", "profile_works", "media_immersive", "article_reader", "homepage_detail":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedListUserPostsClientPresentationContractQueryPresentationRecipes(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedListUserPostsClientPresentationContractQueryPresentationRecipesItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedListUserPostsClientPresentationContractQueryPresentationRecipesItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "cover_media_card", "article_excerpt_card", "homepage_summary_card":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func BindGeneratedListUserPostsClientPresentationContractQuery(r *http.Request) (*GeneratedListUserPostsClientPresentationContractQuery, error) {
	values, err := url.ParseQuery(r.URL.RawQuery)
	if err != nil {
		return nil, fmt.Errorf("invalid query encoding")
	}
	entries, present := values["clientPresentationContract"]
	if !present {
		return nil, nil
	}
	if len(entries) != 1 || strings.TrimSpace(entries[0]) == "" || len(entries[0]) > 8192 || !utf8.ValidString(entries[0]) {
		return nil, fmt.Errorf("invalid JSON query cardinality or byte length")
	}
	decoder := json.NewDecoder(strings.NewReader(entries[0]))
	decoder.UseNumber()
	var raw any
	if err := decoder.Decode(&raw); err != nil {
		return nil, fmt.Errorf("invalid JSON query object")
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		return nil, fmt.Errorf("JSON query contains trailing data")
	}
	if raw == nil {
		return nil, fmt.Errorf("JSON query must be an object")
	}
	if err := validateGeneratedListUserPostsClientPresentationContractQuery(raw); err != nil {
		return nil, err
	}
	var value GeneratedListUserPostsClientPresentationContractQuery
	if err := json.Unmarshal([]byte(entries[0]), &value); err != nil {
		return nil, fmt.Errorf("invalid typed JSON query")
	}
	return &value, nil
}

type GeneratedGetPostClientPresentationContractQuery struct {
	ContentTypes        []string `json:"contentTypes"`
	ContractDigest      string   `json:"contractDigest"`
	ListObjectKinds     []string `json:"listObjectKinds"`
	OpenSurfaces        []string `json:"openSurfaces"`
	PresentationRecipes []string `json:"presentationRecipes"`
}

func validateGeneratedGetPostClientPresentationContractQuery(raw any) error {
	value, ok := raw.(map[string]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	for key := range value {
		switch key {
		case "contentTypes", "contractDigest", "listObjectKinds", "openSurfaces", "presentationRecipes":
		default:
			return fmt.Errorf("invalid typed JSON query field")
		}
	}
	if _, ok := value["contentTypes"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["listObjectKinds"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["presentationRecipes"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["openSurfaces"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if _, ok := value["contractDigest"]; !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if field, ok := value["contentTypes"]; ok {
		if err := validateGeneratedGetPostClientPresentationContractQueryContentTypes(field); err != nil {
			return err
		}
	}
	if field, ok := value["contractDigest"]; ok {
		if err := validateGeneratedGetPostClientPresentationContractQueryContractDigest(field); err != nil {
			return err
		}
	}
	if field, ok := value["listObjectKinds"]; ok {
		if err := validateGeneratedGetPostClientPresentationContractQueryListObjectKinds(field); err != nil {
			return err
		}
	}
	if field, ok := value["openSurfaces"]; ok {
		if err := validateGeneratedGetPostClientPresentationContractQueryOpenSurfaces(field); err != nil {
			return err
		}
	}
	if field, ok := value["presentationRecipes"]; ok {
		if err := validateGeneratedGetPostClientPresentationContractQueryPresentationRecipes(field); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetPostClientPresentationContractQueryContentTypes(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedGetPostClientPresentationContractQueryContentTypesItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetPostClientPresentationContractQueryContentTypesItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "image", "video", "article":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedGetPostClientPresentationContractQueryContractDigest(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	if utf8.RuneCountInString(value) < 71 {
		return fmt.Errorf("JSON query below minimum")
	}
	if utf8.RuneCountInString(value) > 71 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	if matched, err := regexp.MatchString("^sha256:[0-9a-f]{64}$", value); err != nil || !matched {
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedGetPostClientPresentationContractQueryListObjectKinds(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedGetPostClientPresentationContractQueryListObjectKindsItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetPostClientPresentationContractQueryListObjectKindsItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "post", "entity_homepage":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedGetPostClientPresentationContractQueryOpenSurfaces(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedGetPostClientPresentationContractQueryOpenSurfacesItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetPostClientPresentationContractQueryOpenSurfacesItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "home_feed", "profile_works", "media_immersive", "article_reader", "homepage_detail":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func validateGeneratedGetPostClientPresentationContractQueryPresentationRecipes(raw any) error {
	value, ok := raw.([]any)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	if len(value) > 32 {
		return fmt.Errorf("JSON query exceeds maximum")
	}
	for _, item := range value {
		if err := validateGeneratedGetPostClientPresentationContractQueryPresentationRecipesItem(item); err != nil {
			return err
		}
	}
	return nil
}
func validateGeneratedGetPostClientPresentationContractQueryPresentationRecipesItem(raw any) error {
	value, ok := raw.(string)
	if !ok {
		return fmt.Errorf("invalid typed JSON query field")
	}
	_ = value
	switch value {
	case "cover_media_card", "article_excerpt_card", "homepage_summary_card":
	default:
		return fmt.Errorf("invalid typed JSON query field")
	}
	return nil
}
func BindGeneratedGetPostClientPresentationContractQuery(r *http.Request) (*GeneratedGetPostClientPresentationContractQuery, error) {
	values, err := url.ParseQuery(r.URL.RawQuery)
	if err != nil {
		return nil, fmt.Errorf("invalid query encoding")
	}
	entries, present := values["clientPresentationContract"]
	if !present {
		return nil, nil
	}
	if len(entries) != 1 || strings.TrimSpace(entries[0]) == "" || len(entries[0]) > 8192 || !utf8.ValidString(entries[0]) {
		return nil, fmt.Errorf("invalid JSON query cardinality or byte length")
	}
	decoder := json.NewDecoder(strings.NewReader(entries[0]))
	decoder.UseNumber()
	var raw any
	if err := decoder.Decode(&raw); err != nil {
		return nil, fmt.Errorf("invalid JSON query object")
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		return nil, fmt.Errorf("JSON query contains trailing data")
	}
	if raw == nil {
		return nil, fmt.Errorf("JSON query must be an object")
	}
	if err := validateGeneratedGetPostClientPresentationContractQuery(raw); err != nil {
		return nil, err
	}
	var value GeneratedGetPostClientPresentationContractQuery
	if err := json.Unmarshal([]byte(entries[0]), &value); err != nil {
		return nil, fmt.Errorf("invalid typed JSON query")
	}
	return &value, nil
}
