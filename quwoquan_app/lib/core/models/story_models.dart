/// 故事数据模型
class Story {
  final String id;
  final String? authorId;
  final String? imageUrl;
  final Map<String, dynamic>? metadata;
  
  const Story({
    required this.id,
    this.authorId,
    this.imageUrl,
    this.metadata,
  });
  
  factory Story.fromJson(Map<String, dynamic> json) {
    return Story(
      id: json['id']?.toString() ?? '',
      authorId: json['authorId']?.toString(),
      imageUrl: json['imageUrl']?.toString(),
      metadata: json['metadata'] as Map<String, dynamic>?,
    );
  }
  
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'authorId': authorId,
      'imageUrl': imageUrl,
      'metadata': metadata,
    };
  }
}
