String formatCompactActionCount(int count) {
  if (count <= 0) return '0';
  if (count < 1000) return '$count';
  if (count < 10000) {
    return _formatDecimal(
      value: count / 1000,
      suffix: 'k',
      allowDecimal: count < 9950,
    );
  }
  if (count < 100000) {
    return _formatDecimal(
      value: count / 10000,
      suffix: '万',
      allowDecimal: count < 99500,
    );
  }
  if (count < 10000000) {
    return '${count ~/ 10000}万';
  }
  if (count < 100000000) {
    return '${count ~/ 10000000}千万+';
  }
  return '${count ~/ 100000000}亿';
}

String _formatDecimal({
  required double value,
  required String suffix,
  required bool allowDecimal,
}) {
  if (!allowDecimal || value >= 10) {
    return '${value.floor()}$suffix';
  }
  final oneDecimal = value.toStringAsFixed(1);
  final normalized = oneDecimal.endsWith('.0')
      ? oneDecimal.substring(0, oneDecimal.length - 2)
      : oneDecimal;
  return '$normalized$suffix';
}
