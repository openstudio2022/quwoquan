#!/usr/bin/env python3
"""
Figma设计令牌同步脚本 (Python版本)

功能：
1. 从Figma API获取设计令牌（颜色、间距、字体等）
2. 自动生成Flutter设计系统代码
3. 保持与Figma设计的同步

使用方法：
1. 配置 .env 文件，设置 FIGMA_ACCESS_TOKEN 和 FIGMA_FILE_KEY
2. 运行: python3 scripts/sync_figma.py
3. 或者运行: python scripts/sync_figma.py
"""

import os
import sys
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置
CONFIG = {
    'api_url': 'https://api.figma.com/v1',
    'access_token': os.getenv('FIGMA_ACCESS_TOKEN'),
    'file_key': os.getenv('FIGMA_FILE_KEY'),
    'design_tokens_node_id': os.getenv('FIGMA_DESIGN_TOKENS_NODE_ID'),
    'output_dir': Path(__file__).parent.parent / 'lib' / 'core' / 'design_system',
}


def check_config():
    """检查配置是否完整"""
    if not CONFIG['access_token']:
        print('❌ 错误: 未设置 FIGMA_ACCESS_TOKEN')
        print('请在 .env 文件中设置你的 Figma Access Token')
        sys.exit(1)
    
    if not CONFIG['file_key']:
        print('❌ 错误: 未设置 FIGMA_FILE_KEY')
        print('请在 .env 文件中设置你的 Figma File Key')
        sys.exit(1)


def figma_request(endpoint: str) -> Dict[str, Any]:
    """发送Figma API请求"""
    url = f"{CONFIG['api_url']}{endpoint}"
    headers = {
        'X-Figma-Token': CONFIG['access_token'],
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f'API请求失败: {e}')


def get_figma_file() -> Dict[str, Any]:
    """获取Figma文件"""
    print('📥 正在从Figma获取文件...')
    try:
        data = figma_request(f"/files/{CONFIG['file_key']}")
        return data
    except Exception as e:
        print(f'❌ 获取Figma文件失败: {e}')
        raise


def find_node_by_name(nodes: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """按名称查找节点"""
    if isinstance(nodes, dict):
        for node_id, node in nodes.items():
            if isinstance(node, dict) and node.get('name') == name:
                return node
            if isinstance(node, dict) and 'children' in node:
                found = find_node_by_name(node['children'], name)
                if found:
                    return found
    return None


def rgb_to_hex(r: float, g: float, b: float) -> str:
    """RGB转HEX"""
    def to_hex(n: float) -> str:
        hex_val = hex(int(n * 255))[2:]
        return hex_val.zfill(2)
    return f"#{to_hex(r)}{to_hex(g)}{to_hex(b)}".upper()


def extract_colors(node: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """提取颜色令牌"""
    colors = {}
    
    def traverse(n: Dict[str, Any]):
        if n.get('type') == 'RECTANGLE' and 'fills' in n and n['fills']:
            fill = n['fills'][0]
            if fill.get('type') == 'SOLID':
                color = fill['color']
                hex_color = rgb_to_hex(color['r'], color['g'], color['b'])
                name = n.get('name', '').lower().replace(' ', '')
                colors[name] = {
                    'hex': hex_color,
                    'rgba': f"rgba({int(color['r'] * 255)}, {int(color['g'] * 255)}, {int(color['b'] * 255)}, {fill.get('opacity', 1)})",
                }
        
        if 'children' in n:
            for child in n['children']:
                traverse(child)
    
    traverse(node)
    return colors


def extract_spacing(node: Dict[str, Any]) -> Dict[str, float]:
    """提取间距令牌"""
    spacing = {}
    
    def traverse(n: Dict[str, Any]):
        node_type = n.get('type', '')
        if node_type in ['FRAME', 'GROUP']:
            name = n.get('name', '').lower().replace(' ', '')
            if 'spacing' in name or 'gap' in name:
                # 尝试从名称中提取数值
                import re
                match = re.search(r'(\d+)', n.get('name', ''))
                if match:
                    spacing[name] = float(match.group(1))
        
        if 'children' in n:
            for child in n['children']:
                traverse(child)
    
    traverse(node)
    return spacing


def hex_to_int(hex_color: str) -> str:
    """HEX转整数（用于Color构造函数）"""
    return hex_color.replace('#', '').zfill(8).replace(' ', 'FF')


def generate_colors_code(colors: Dict[str, Dict[str, str]]) -> str:
    """生成颜色代码"""
    lines = [
        "import 'package:flutter/material.dart';",
        "",
        "/// 应用颜色常量",
        "/// 此文件由Figma同步脚本自动生成，请勿手动修改",
        "class AppColors {",
    ]
    
    # 主色调
    if 'primary' in colors or 'primarycolor' in colors:
        primary = colors.get('primary') or colors.get('primarycolor')
        lines.append(f"  static const Color primaryColor = Color(0x{hex_to_int(primary['hex'])});")
    
    if 'secondary' in colors or 'secondarycolor' in colors:
        secondary = colors.get('secondary') or colors.get('secondarycolor')
        lines.append(f"  static const Color secondaryColor = Color(0x{hex_to_int(secondary['hex'])});")
    
    # 功能性颜色
    if 'success' in colors:
        lines.append(f"  static const Color success = Color(0x{hex_to_int(colors['success']['hex'])});")
    if 'warning' in colors:
        lines.append(f"  static const Color warning = Color(0x{hex_to_int(colors['warning']['hex'])});")
    if 'error' in colors:
        lines.append(f"  static const Color error = Color(0x{hex_to_int(colors['error']['hex'])});")
    
    lines.append("")
    lines.append("  static final AppColorsTheme dark = AppColorsTheme(isDark: true);")
    lines.append("  static final AppColorsTheme light = AppColorsTheme(isDark: false);")
    lines.append("}")
    lines.append("")
    lines.append("class AppColorsTheme {")
    lines.append("  final bool isDark;")
    lines.append("  ")
    lines.append("  AppColorsTheme({required this.isDark});")
    lines.append("  ")
    lines.append("  Color get backgroundPrimary => isDark ? Colors.black : Colors.white;")
    lines.append("  Color get backgroundSecondary => isDark ? Colors.grey[800]! : Colors.grey[200]!;")
    lines.append("  Color get textPrimary => isDark ? Colors.white : Colors.black;")
    lines.append("  Color get textSecondary => isDark ? Colors.grey[300]! : Colors.grey[700]!;")
    lines.append("}")
    
    return '\n'.join(lines)


def generate_spacing_code(spacing: Dict[str, float]) -> str:
    """生成间距代码"""
    lines = [
        "/// 应用间距常量",
        "/// 此文件由Figma同步脚本自动生成，请勿手动修改",
        "class AppSpacing {",
        "  // 基础间距",
    ]
    
    # 标准间距值
    standard_spacing = {
        'xs': spacing.get('xs') or spacing.get('spacing-xs', 4.0),
        'sm': spacing.get('sm') or spacing.get('spacing-sm', 8.0),
        'md': spacing.get('md') or spacing.get('spacing-md', 16.0),
        'lg': spacing.get('lg') or spacing.get('spacing-lg', 24.0),
        'xl': spacing.get('xl') or spacing.get('spacing-xl', 32.0),
    }
    
    for key, value in standard_spacing.items():
        lines.append(f"  static const double {key} = {value};")
    
    lines.append("}")
    return '\n'.join(lines)


def save_file(file_path: Path, content: str):
    """保存文件"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding='utf-8')
    print(f"✅ 已生成: {file_path}")


def main():
    """主函数"""
    print('🚀 开始同步Figma设计令牌...\n')
    
    check_config()
    
    try:
        # 获取Figma文件
        file_data = get_figma_file()
        print(f"✅ 成功获取Figma文件: {file_data.get('name', 'Unknown')}\n")
        
        # 获取文档节点
        document = file_data.get('document', {})
        
        # 查找设计令牌节点
        design_tokens_node = None
        if CONFIG['design_tokens_node_id']:
            # 需要先获取节点详情
            node_data = figma_request(f"/files/{CONFIG['file_key']}/nodes?ids={CONFIG['design_tokens_node_id']}")
            design_tokens_node = node_data.get('nodes', {}).get(CONFIG['design_tokens_node_id'])
        else:
            # 尝试从文档中查找
            design_tokens_node = find_node_by_name({document.get('id'): document}, 'Design Tokens')
        
        if not design_tokens_node:
            print('⚠️  未找到设计令牌节点，将使用默认值')
            print('💡 提示: 可以在Figma中创建名为"Design Tokens"的页面，或设置 FIGMA_DESIGN_TOKENS_NODE_ID\n')
        
        # 提取颜色
        print('🎨 提取颜色令牌...')
        colors = extract_colors(design_tokens_node) if design_tokens_node else {}
        if colors:
            colors_code = generate_colors_code(colors)
            save_file(CONFIG['output_dir'] / 'colors' / 'app_colors.dart', colors_code)
        else:
            print('⚠️  未找到颜色令牌，跳过颜色同步')
        
        # 提取间距
        print('📏 提取间距令牌...')
        spacing = extract_spacing(design_tokens_node) if design_tokens_node else {}
        if spacing:
            spacing_code = generate_spacing_code(spacing)
            save_file(CONFIG['output_dir'] / 'spacing' / 'app_spacing.dart', spacing_code)
        else:
            print('⚠️  未找到间距令牌，跳过间距同步')
        
        print('\n✨ Figma同步完成！')
        print('\n📝 下一步:')
        print('1. 检查生成的文件是否符合预期')
        print('2. 运行 flutter analyze 检查代码')
        print('3. 运行 flutter test 确保测试通过')
        
    except Exception as error:
        print(f'\n❌ 同步失败: {error}')
        sys.exit(1)


if __name__ == '__main__':
    main()

