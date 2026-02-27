import 'package:flutter/material.dart';

/// 私人助理头像：紫渐变圆 + 白色星形图标（用于趣聊列表与对话气泡）
class AssistantAvatar extends StatelessWidget {
  const AssistantAvatar({
    super.key,
    this.radius = 20,
    this.onTap,
  });

  final double radius;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final size = radius * 2;
    final box = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF6366F1),
            Color(0xFF8B5CF6),
            Color(0xFFA855F7),
          ],
        ),
        boxShadow: [
          BoxShadow(
            color: Color(0xFF8B5CF6).withValues(alpha: 0.3),
            blurRadius: 6,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Center(
        child: Icon(
          Icons.auto_awesome,
          size: radius * 1.0,
          color: Colors.white,
        ),
      ),
    );
    if (onTap != null) {
      return GestureDetector(
        onTap: onTap,
        child: box,
      );
    }
    return box;
  }
}
