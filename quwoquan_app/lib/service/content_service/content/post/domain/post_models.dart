/// 帖子数据模型
class Post {
  final String id;
  final String? authorId;
  final String? content;
  final Map<String, dynamic>? metadata;

  const Post({required this.id, this.authorId, this.content, this.metadata});
}
