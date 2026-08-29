// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#req-006
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-003
package publicweb_test

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"

	"golang.org/x/net/html"

	publicweb "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/publicweb"
)

type markdownBlockSequenceContract struct {
	Schema string                      `json:"schema"`
	Cases  []markdownBlockSequenceCase `json:"cases"`
}

type markdownBlockSequenceCase struct {
	Name                string             `json:"name"`
	Markdown            string             `json:"markdown"`
	Assets              []fixtureBodyAsset `json:"assets"`
	ExpectedSequence    []semanticBlock    `json:"expectedSequence"`
	ExpectedFingerprint string             `json:"expectedFingerprint"`
}

type fixtureBodyAsset struct {
	AssetID string `json:"assetId"`
	URL     string `json:"cdnUrl"`
	Caption string `json:"caption"`
}

type semanticBlock struct {
	Type    string `json:"type"`
	AssetID string `json:"assetId"`
}

func TestPublicWebMarkdownMatchesSharedSemanticBlockSequence(t *testing.T) {
	contract := loadMarkdownBlockSequenceContract(t)
	if contract.Schema != "content_post_markdown_block_sequence_cases" || len(contract.Cases) == 0 {
		t.Fatalf("invalid shared block-sequence contract: schema=%q cases=%d", contract.Schema, len(contract.Cases))
	}

	for _, fixtureCase := range contract.Cases {
		t.Run(fixtureCase.Name, func(t *testing.T) {
			assets := make(map[string]publicweb.BodyAsset, len(fixtureCase.Assets))
			for _, asset := range fixtureCase.Assets {
				assets[asset.AssetID] = publicweb.BodyAsset{
					URL:     asset.URL,
					Caption: asset.Caption,
				}
			}
			rendered := publicweb.RenderQwqMarkdownBodyHTML(fixtureCase.Markdown, assets)
			observed := semanticBlocksFromHTML(t, rendered)

			if !reflect.DeepEqual(observed, fixtureCase.ExpectedSequence) {
				t.Fatalf("semantic block sequence drift\nobserved: %#v\nexpected: %#v\nhtml: %s", observed, fixtureCase.ExpectedSequence, rendered)
			}
			if fingerprint := semanticBlockFingerprint(observed); fingerprint != fixtureCase.ExpectedFingerprint {
				t.Fatalf("semantic block fingerprint=%s want=%s", fingerprint, fixtureCase.ExpectedFingerprint)
			}
		})
	}
}

func TestPublicWebMarkdownClosesCalloutAtEOF(t *testing.T) {
	rendered := publicweb.RenderQwqMarkdownBodyHTML(
		":::callout type=\"tip\"\n未闭合提示仍需生成有效 HTML。",
		nil,
	)
	const expected = `<aside class="qwq-callout"><p>未闭合提示仍需生成有效 HTML。</p></aside>`
	if rendered != expected {
		t.Fatalf("unclosed callout html=%q want=%q", rendered, expected)
	}
}

func loadMarkdownBlockSequenceContract(t *testing.T) markdownBlockSequenceContract {
	t.Helper()
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve current test file")
	}
	root := filepath.Dir(currentFile)
	for filepath.Base(root) != "quwoquan_service" {
		parent := filepath.Dir(root)
		if parent == root {
			t.Fatal("quwoquan_service root not found")
		}
		root = parent
	}
	path := filepath.Join(
		root,
		"services/content-service/contracts/content/post/markdown_block_sequence_cases.json",
	)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read shared block-sequence contract: %v", err)
	}
	var contract markdownBlockSequenceContract
	if err := json.Unmarshal(raw, &contract); err != nil {
		t.Fatalf("decode shared block-sequence contract: %v", err)
	}
	return contract
}

func semanticBlocksFromHTML(t *testing.T, fragment string) []semanticBlock {
	t.Helper()
	tokenizer := html.NewTokenizer(strings.NewReader(fragment))
	blocks := make([]semanticBlock, 0)
	listKinds := make([]string, 0, 2)
	blockquoteDepth := 0
	calloutDepth := 0
	preDepth := 0

	for {
		switch tokenizer.Next() {
		case html.ErrorToken:
			if err := tokenizer.Err(); err != io.EOF {
				t.Fatalf("tokenize rendered HTML: %v", err)
			}
			return blocks
		case html.StartTagToken, html.SelfClosingTagToken:
			token := tokenizer.Token()
			switch token.Data {
			case "h2":
				blocks = append(blocks, semanticBlock{Type: "heading2"})
			case "h3":
				blocks = append(blocks, semanticBlock{Type: "heading3"})
			case "p":
				if blockquoteDepth == 0 && calloutDepth == 0 {
					blocks = append(blocks, semanticBlock{Type: "paragraph"})
				}
			case "ol":
				listKinds = append(listKinds, "orderedItem")
			case "ul":
				listKinds = append(listKinds, "bulletItem")
			case "li":
				if len(listKinds) == 0 {
					t.Fatal("list item rendered without list container")
				}
				blocks = append(blocks, semanticBlock{Type: listKinds[len(listKinds)-1]})
			case "blockquote":
				blocks = append(blocks, semanticBlock{Type: "quote"})
				blockquoteDepth++
			case "aside":
				if hasHTMLClass(token, "qwq-callout") {
					blocks = append(blocks, semanticBlock{Type: "callout"})
					calloutDepth++
				}
			case "pre":
				blocks = append(blocks, semanticBlock{Type: "codeBlock"})
				preDepth++
			case "hr":
				blocks = append(blocks, semanticBlock{Type: "divider"})
			case "img":
				blocks = append(blocks, semanticBlock{
					Type:    "image",
					AssetID: htmlAttribute(token, "data-asset-id"),
				})
			}
		case html.EndTagToken:
			token := tokenizer.Token()
			switch token.Data {
			case "ol", "ul":
				if len(listKinds) > 0 {
					listKinds = listKinds[:len(listKinds)-1]
				}
			case "blockquote":
				if blockquoteDepth > 0 {
					blockquoteDepth--
				}
			case "aside":
				if calloutDepth > 0 {
					calloutDepth--
				}
			case "pre":
				if preDepth > 0 {
					preDepth--
				}
			}
		}
	}
}

func hasHTMLClass(token html.Token, expected string) bool {
	for _, attribute := range token.Attr {
		if attribute.Key == "class" {
			for _, className := range strings.Fields(attribute.Val) {
				if className == expected {
					return true
				}
			}
		}
	}
	return false
}

func htmlAttribute(token html.Token, key string) string {
	for _, attribute := range token.Attr {
		if attribute.Key == key {
			return attribute.Val
		}
	}
	return ""
}

func semanticBlockFingerprint(sequence []semanticBlock) string {
	rows := make([]string, 0, len(sequence))
	for _, block := range sequence {
		rows = append(rows, block.Type+"|"+block.AssetID)
	}
	digest := sha256.Sum256([]byte(strings.Join(rows, "\n")))
	return hex.EncodeToString(digest[:])
}
