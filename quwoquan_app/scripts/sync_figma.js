#!/usr/bin/env node

/**
 * Figma设计令牌同步脚本
 * 
 * 功能：
 * 1. 从Figma API获取设计令牌（颜色、间距、字体等）
 * 2. 自动生成Flutter设计系统代码
 * 3. 保持与Figma设计的同步
 * 
 * 使用方法：
 * 1. 配置 .env 文件，设置 FIGMA_ACCESS_TOKEN 和 FIGMA_FILE_KEY
 * 2. 运行: node scripts/sync_figma.js
 * 3. 或者运行: npm run sync:figma
 */

const https = require('https');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

// 配置
const CONFIG = {
  apiUrl: 'https://api.figma.com/v1',
  accessToken: process.env.FIGMA_ACCESS_TOKEN,
  fileKey: process.env.FIGMA_FILE_KEY,
  designTokensNodeId: process.env.FIGMA_DESIGN_TOKENS_NODE_ID,
  outputDir: path.join(__dirname, '../lib/core/design_system'),
};

// 检查配置
if (!CONFIG.accessToken) {
  console.error('❌ 错误: 未设置 FIGMA_ACCESS_TOKEN');
  console.log('请在 .env 文件中设置你的 Figma Access Token');
  process.exit(1);
}

if (!CONFIG.fileKey) {
  console.error('❌ 错误: 未设置 FIGMA_FILE_KEY');
  console.log('请在 .env 文件中设置你的 Figma File Key');
  process.exit(1);
}

/**
 * 发送Figma API请求
 */
function figmaRequest(endpoint) {
  return new Promise((resolve, reject) => {
    const url = `${CONFIG.apiUrl}${endpoint}`;
    const options = {
      headers: {
        'X-Figma-Token': CONFIG.accessToken,
      },
    };

    https.get(url, options, (res) => {
      let data = '';

      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        if (res.statusCode === 200) {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            reject(new Error(`解析JSON失败: ${e.message}`));
          }
        } else {
          reject(new Error(`API请求失败: ${res.statusCode} - ${data}`));
        }
      });
    }).on('error', (err) => {
      reject(err);
    });
  });
}

/**
 * 获取Figma文件
 */
async function getFigmaFile() {
  console.log('📥 正在从Figma获取文件...');
  try {
    const data = await figmaRequest(`/files/${CONFIG.fileKey}`);
    return data;
  } catch (error) {
    console.error('❌ 获取Figma文件失败:', error.message);
    throw error;
  }
}

/**
 * 获取设计令牌节点
 */
function findDesignTokensNode(nodes, nodeId) {
  if (!nodeId) {
    // 如果没有指定节点ID，尝试查找名为"Design Tokens"的节点
    return findNodeByName(nodes, 'Design Tokens');
  }
  return nodes[nodeId];
}

/**
 * 按名称查找节点
 */
function findNodeByName(nodes, name) {
  for (const nodeId in nodes) {
    const node = nodes[nodeId];
    if (node.name === name) {
      return node;
    }
    if (node.children) {
      const found = findNodeByName(node.children, name);
      if (found) return found;
    }
  }
  return null;
}

/**
 * 提取颜色令牌
 */
function extractColors(node) {
  const colors = {};
  
  function traverse(n) {
    if (n.type === 'RECTANGLE' && n.fills && n.fills.length > 0) {
      const fill = n.fills[0];
      if (fill.type === 'SOLID') {
        const color = fill.color;
        const hex = rgbToHex(color.r, color.g, color.b);
        const name = n.name.toLowerCase().replace(/\s+/g, '');
        colors[name] = {
          hex,
          rgba: `rgba(${Math.round(color.r * 255)}, ${Math.round(color.g * 255)}, ${Math.round(color.b * 255)}, ${fill.opacity || 1})`,
        };
      }
    }
    
    if (n.children) {
      n.children.forEach(traverse);
    }
  }
  
  traverse(node);
  return colors;
}

/**
 * RGB转HEX
 */
function rgbToHex(r, g, b) {
  const toHex = (n) => {
    const hex = Math.round(n * 255).toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  };
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase();
}

/**
 * 提取间距令牌
 */
function extractSpacing(node) {
  const spacing = {};
  
  function traverse(n) {
    if (n.type === 'FRAME' || n.type === 'GROUP') {
      const name = n.name.toLowerCase().replace(/\s+/g, '');
      if (name.includes('spacing') || name.includes('gap')) {
        // 尝试从名称或尺寸中提取间距值
        const match = n.name.match(/(\d+)/);
        if (match) {
          spacing[name] = parseFloat(match[1]);
        }
      }
    }
    
    if (n.children) {
      n.children.forEach(traverse);
    }
  }
  
  traverse(node);
  return spacing;
}

/**
 * 生成颜色代码
 */
function generateColorsCode(colors) {
  const lines = [
    "import 'package:flutter/material.dart';",
    "",
    "class AppColors {",
  ];

  // 主色调
  if (colors.primary || colors.primarycolor) {
    const primary = colors.primary || colors.primarycolor;
    lines.push(`  static const Color primaryColor = Color(0x${hexToInt(primary.hex)});`);
  }
  
  if (colors.secondary || colors.secondarycolor) {
    const secondary = colors.secondary || colors.secondarycolor;
    lines.push(`  static const Color secondaryColor = Color(0x${hexToInt(secondary.hex)});`);
  }

  // 功能性颜色
  if (colors.success) {
    lines.push(`  static const Color success = Color(0x${hexToInt(colors.success.hex)});`);
  }
  if (colors.warning) {
    lines.push(`  static const Color warning = Color(0x${hexToInt(colors.warning.hex)});`);
  }
  if (colors.error) {
    lines.push(`  static const Color error = Color(0x${hexToInt(colors.error.hex)});`);
  }

  lines.push("");
  lines.push("  static final AppColorsTheme dark = AppColorsTheme(isDark: true);");
  lines.push("  static final AppColorsTheme light = AppColorsTheme(isDark: false);");
  lines.push("}");
  lines.push("");
  lines.push("class AppColorsTheme {");
  lines.push("  final bool isDark;");
  lines.push("  ");
  lines.push("  AppColorsTheme({required this.isDark});");
  lines.push("  ");
  lines.push("  Color get backgroundPrimary => isDark ? Colors.black : Colors.white;");
  lines.push("  Color get backgroundSecondary => isDark ? Colors.grey[800]! : Colors.grey[200]!;");
  lines.push("  Color get textPrimary => isDark ? Colors.white : Colors.black;");
  lines.push("  Color get textSecondary => isDark ? Colors.grey[300]! : Colors.grey[700]!;");
  lines.push("}");

  return lines.join('\n');
}

/**
 * HEX转整数（用于Color构造函数）
 */
function hexToInt(hex) {
  return hex.replace('#', '').padStart(8, 'FF');
}

/**
 * 生成间距代码
 */
function generateSpacingCode(spacing) {
  const lines = [
    "/// 应用间距常量",
    "/// 此文件由Figma同步脚本自动生成，请勿手动修改",
    "class AppSpacing {",
    "  // 基础间距",
  ];

  // 标准间距值
  const standardSpacing = {
    xs: spacing.xs || spacing['spacing-xs'] || 4.0,
    sm: spacing.sm || spacing['spacing-sm'] || 8.0,
    md: spacing.md || spacing['spacing-md'] || 16.0,
    lg: spacing.lg || spacing['spacing-lg'] || 24.0,
    xl: spacing.xl || spacing['spacing-xl'] || 32.0,
  };

  Object.entries(standardSpacing).forEach(([key, value]) => {
    lines.push(`  static const double ${key} = ${value};`);
  });

  lines.push("}");
  return lines.join('\n');
}

/**
 * 保存文件
 */
function saveFile(filePath, content) {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(filePath, content, 'utf8');
  console.log(`✅ 已生成: ${filePath}`);
}

/**
 * 主函数
 */
async function main() {
  console.log('🚀 开始同步Figma设计令牌...\n');

  try {
    // 获取Figma文件
    const fileData = await getFigmaFile();
    console.log(`✅ 成功获取Figma文件: ${fileData.name}\n`);

    // 获取文档节点
    const document = fileData.document;
    const nodes = fileData.styles || {};

    // 查找设计令牌节点
    let designTokensNode = null;
    if (CONFIG.designTokensNodeId) {
      // 需要先获取节点详情
      const nodeData = await figmaRequest(`/files/${CONFIG.fileKey}/nodes?ids=${CONFIG.designTokensNodeId}`);
      designTokensNode = nodeData.nodes[CONFIG.designTokensNodeId];
    } else {
      // 尝试从文档中查找
      designTokensNode = findDesignTokensNode({ [document.id]: document }, null);
    }

    if (!designTokensNode) {
      console.warn('⚠️  未找到设计令牌节点，将使用默认值');
      console.log('💡 提示: 可以在Figma中创建名为"Design Tokens"的页面，或设置 FIGMA_DESIGN_TOKENS_NODE_ID\n');
    }

    // 提取颜色
    console.log('🎨 提取颜色令牌...');
    const colors = designTokensNode ? extractColors(designTokensNode) : {};
    if (Object.keys(colors).length > 0) {
      const colorsCode = generateColorsCode(colors);
      saveFile(path.join(CONFIG.outputDir, 'colors/app_colors.dart'), colorsCode);
    } else {
      console.log('⚠️  未找到颜色令牌，跳过颜色同步');
    }

    // 提取间距
    console.log('📏 提取间距令牌...');
    const spacing = designTokensNode ? extractSpacing(designTokensNode) : {};
    if (Object.keys(spacing).length > 0) {
      const spacingCode = generateSpacingCode(spacing);
      saveFile(path.join(CONFIG.outputDir, 'spacing/app_spacing.dart'), spacingCode);
    } else {
      console.log('⚠️  未找到间距令牌，跳过间距同步');
    }

    console.log('\n✨ Figma同步完成！');
    console.log('\n📝 下一步:');
    console.log('1. 检查生成的文件是否符合预期');
    console.log('2. 运行 flutter analyze 检查代码');
    console.log('3. 运行 flutter test 确保测试通过');

  } catch (error) {
    console.error('\n❌ 同步失败:', error.message);
    process.exit(1);
  }
}

// 运行主函数
if (require.main === module) {
  main();
}

module.exports = { main, figmaRequest, extractColors, extractSpacing };

