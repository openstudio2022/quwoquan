/// 帖子数据模型
class Post {
  final String id;
  final String? authorId;
  final String? content;
  final Map<String, dynamic>? metadata;
  
  const Post({
    required this.id,
    this.authorId,
    this.content,
    this.metadata,
  });
  
  factory Post.fromJson(Map<String, dynamic> json) {
    return Post(
      id: json['id']?.toString() ?? '',
      authorId: json['authorId']?.toString(),
      content: json['content']?.toString(),
      metadata: json['metadata'] as Map<String, dynamic>?,
    );
  }
  
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'authorId': authorId,
      'content': content,
      'metadata': metadata,
    };
  }
}

