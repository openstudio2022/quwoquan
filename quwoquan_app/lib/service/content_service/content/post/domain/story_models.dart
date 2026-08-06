/// 故事数据模型
class Story {
  final String id;
  final String? authorId;
  final String? imageUrl;
  final Map<String, dynamic>? metadata;

  const Story({required this.id, this.authorId, this.imageUrl, this.metadata});
}
