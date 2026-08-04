package model

// CitationDestination 是引用跳转的唯一 wire 形态：站内引用只传 canonical
// object type/id，站外引用只传已验证 HTTPS URL。
type CitationDestination struct {
	Kind          string `json:"kind" bson:"kind"`
	ObjectTypeRef string `json:"objectTypeRef,omitempty" bson:"objectTypeRef,omitempty"`
	ObjectID      string `json:"objectId,omitempty" bson:"objectId,omitempty"`
	URL           string `json:"url,omitempty" bson:"url,omitempty"`
}
