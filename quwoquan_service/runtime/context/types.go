package runtimecontext

import "time"

type PageType string

const (
	PageFeed           PageType = "feed"
	PageContentDetail  PageType = "content_detail"
	PageChat           PageType = "chat"
	PageGroupChat      PageType = "group_chat"
	PageCircle         PageType = "circle"
	PageCircleDiscover PageType = "circle_discover"
	PageSearch         PageType = "search"
	PageUserProfile    PageType = "user_profile"
)

type PageContextRequest struct {
	UserID      string            `json:"userId"`
	SessionID   string            `json:"sessionId"`
	PageType    PageType          `json:"pageType"`
	Objects     PageObjects       `json:"objects"`
	UserAction  string            `json:"userAction"`
	UserActions []UserActionEvent `json:"userActions,omitempty"`
}

type UserActionEvent struct {
	Action    string    `json:"action"`
	ObjectID  string    `json:"objectId"`
	Body      string    `json:"body,omitempty"`
	Target    string    `json:"target,omitempty"`
	Timestamp time.Time `json:"timestamp"`
}

type PageObjects struct {
	Post         *PostSnapshot         `json:"post,omitempty"`
	Posts        []PostBrief           `json:"posts,omitempty"`
	Conversation *ConversationSnapshot `json:"conversation,omitempty"`
	Circle       *CircleSnapshot       `json:"circle,omitempty"`
	SearchQuery  string                `json:"searchQuery,omitempty"`
	TargetUser   *UserBrief            `json:"targetUser,omitempty"`
}

type PostSnapshot struct {
	ID          string         `json:"id"`
	ContentType string         `json:"contentType"`
	Title       string         `json:"title"`
	Body        string         `json:"body,omitempty"`
	Tags        []string       `json:"tags,omitempty"`
	MediaURLs   []string       `json:"mediaUrls,omitempty"`
	Author      UserBrief      `json:"author"`
	Comments    []CommentBrief `json:"comments,omitempty"`
	Location    *GeoPoint      `json:"location,omitempty"`
}

type PostBrief struct {
	ID          string   `json:"id"`
	ContentType string   `json:"contentType"`
	Title       string   `json:"title,omitempty"`
	Tags        []string `json:"tags,omitempty"`
	AuthorID    string   `json:"authorId"`
}

type ConversationSnapshot struct {
	ConversationID string         `json:"conversationId"`
	Type           string         `json:"type"`
	Participants   []UserBrief    `json:"participants"`
	RecentMessages []MessageBrief `json:"recentMessages,omitempty"`
}

type MessageBrief struct {
	SenderID  string    `json:"senderId"`
	Content   string    `json:"content"`
	Timestamp time.Time `json:"timestamp"`
}

type CircleSnapshot struct {
	CircleID    string      `json:"circleId"`
	Name        string      `json:"name"`
	Description string      `json:"description,omitempty"`
	Tags        []string    `json:"tags,omitempty"`
	Members     []UserBrief `json:"members,omitempty"`
}

type UserBrief struct {
	UserID   string `json:"userId"`
	Nickname string `json:"nickname"`
	Avatar   string `json:"avatar,omitempty"`
}

type CommentBrief struct {
	AuthorID  string    `json:"authorId"`
	Content   string    `json:"content"`
	Timestamp time.Time `json:"timestamp"`
}

type GeoPoint struct {
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
}

type PageContextSnapshot struct {
	UserID     string      `json:"userId"`
	SessionID  string      `json:"sessionId"`
	PageType   PageType    `json:"pageType"`
	Objects    PageObjects `json:"objects"`
	UserAction string      `json:"userAction"`
	CapturedAt time.Time   `json:"capturedAt"`
}

type SessionSignalSnapshot struct {
	TagWeights    map[string]float64 `json:"tagWeights"`
	ExposedCount  int                `json:"exposedCount"`
	NegativeCount int                `json:"negativeCount"`
	TopInterests  []string           `json:"topInterests"`
}

type UserHolisticProfile struct {
	UserID            string           `json:"userId"            bson:"userId"`
	ContentPreference ProfileDimension `json:"contentPreference" bson:"contentPreference"`
	SocialGraph       ProfileDimension `json:"socialGraph"       bson:"socialGraph"`
	CircleActivity    ProfileDimension `json:"circleActivity"    bson:"circleActivity"`
	ChatTopics        ProfileDimension `json:"chatTopics"        bson:"chatTopics"`
	AssistantHistory  ProfileDimension `json:"assistantHistory"  bson:"assistantHistory"`
	UpdatedAt         time.Time        `json:"updatedAt"         bson:"updatedAt"`
}

type ProfileDimension struct {
	Tags       map[string]float64 `json:"tags"       bson:"tags"`
	Summary    string             `json:"summary"    bson:"summary"`
	EventCount int64              `json:"eventCount" bson:"eventCount"`
}

type AssistantContext struct {
	PageContext      *PageContextSnapshot   `json:"pageContext,omitempty"`
	SessionSignals   *SessionSignalSnapshot `json:"sessionSignals,omitempty"`
	HolisticProfile  *UserHolisticProfile   `json:"holisticProfile,omitempty"`
	RelevantMemories []RetrievedChunk       `json:"relevantMemories,omitempty"`
	RelevantContent  []RetrievedChunk       `json:"relevantContent,omitempty"`
}

type RetrievedChunk struct {
	ID      string  `json:"id"`
	Content string  `json:"content"`
	Score   float64 `json:"score"`
	Source  string  `json:"source"`
}
