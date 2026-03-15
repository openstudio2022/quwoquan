class MCPBridge {
  const MCPBridge();

  Future<Map<String, dynamic>> invoke({
    required String method,
    Map<String, dynamic> arguments = const <String, dynamic>{},
  }) async {
    return <String, dynamic>{
      'success': false,
      'method': method,
      'message': 'MCP bridge is reserved for future integration.',
      'arguments': arguments,
    };
  }
}
