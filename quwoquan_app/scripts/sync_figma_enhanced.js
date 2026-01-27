#!/usr/bin/env node

/**
 * Figma设计令牌同步脚本（增强版）
 * 
 * 功能：
 * 1. 从Figma API获取设计令牌（颜色、间距、字体等）
 * 2. 从Figma变量（Variables）和样式（Styles）中提取
 * 3. 自动生成Flutter设计系统代码
 * 4. 保持与Figma设计的同步
 * 
 * 使用方法：
 * 1. 配置 .env 文件，设置 FIGMA_ACCESS_TOKEN 和 FIGMA_FILE_KEY
 * 2. 运行: node scripts/sync_figma_enhanced.js
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
  console.log('或运行: bash scripts/setup_figma_config.sh');
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
          const errorData = JSON.parse(data);
          reject(new Error(`API请求失败: ${res.statusCode} - ${errorData.err || data}`));
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
    // 检查是否是文件类型不支持的错误
    if (error.message.includes('File type not supported') || error.message.includes('400')) {
      console.error('❌ 获取Figma文件失败:', error.message);
      console.log('');
      console.log('💡 问题分析:');
      console.log('  这个错误通常表示文件是社区文件(/make/)或模板，无法通过标准API访问。');
      console.log('');
      console.log('🔧 解决方案:');
      console.log('  1. 如果是社区文件，需要先复制到你的工作区:');
      console.log('     - 在Figma中打开文件');
      console.log('     - 点击右上角 "..." → "Duplicate" 复制到你的工作区');
      console.log('     - 使用新文件的URL（格式: /file/FILE_KEY/File-Name）');
      console.log('');
      console.log('  2. 如果是团队文件，确保:');
      console.log('     - 你是团队成员');
      console.log('     - 文件URL格式是 /file/ 而不是 /make/');
      console.log('     - 访问令牌有读取权限');
      console.log('');
      console.log('  3. 获取正确的文件ID:');
      console.log('     - 标准文件URL: https://www.figma.com/file/FILE_KEY/File-Name');
      console.log('     - FILE_KEY 就是文件ID');
      console.log('');
    } else {
      console.error('❌ 获取Figma文件失败:', error.message);
    }
    throw error;
  }
}

/**
 * 获取Figma变量
 */
async function getFigmaVariables() {
  console.log('📥 正在获取Figma变量...');
  try {
    const data = await figmaRequest(`/files/${CONFIG.fileKey}/variables/local`);
    return data;
  } catch (error) {
    console.warn('⚠️  获取Figma变量失败（可能文件没有使用变量）:', error.message);
    return null;
  }
}

/**
 * 获取Figma样式
 */
async function getFigmaStyles() {
  console.log('📥 正在获取Figma样式...');
  try {
    const data = await figmaRequest(`/files/${CONFIG.fileKey}/styles`);
    return data;
  } catch (error) {
    console.warn('⚠️  获取Figma样式失败:', error.message);
    return null;
  }
}

/**
 * 递归查找节点
 */
function findNodeByName(nodes, name, exact = false) {
  if (!nodes) return null;
  
  for (const nodeId in nodes) {
    const node = nodes[nodeId];
    const nodeName = node.name || '';
    
    if (exact ? nodeName === name : nodeName.toLowerCase().includes(name.toLowerCase())) {
      return node;
    }
    
    if (node.children) {
      const found = findNodeByName(node.children, name, exact);
      if (found) return found;
    }
  }
  return null;
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
 * 从变量中提取颜色
 */
function extractColorsFromVariables(variables) {
  const colors = {};
  
  if (!variables || !variables.meta) return colors;
  
  for (const variableId in variables.meta.variables) {
    const variable = variables.meta.variables[variableId];
    if (variable.resolvedType === 'COLOR') {
      const name = variable.name.toLowerCase().replace(/[^a-z0-9]/g, '');
      const values = variable.valuesByMode;
      
      // 获取第一个模式的值
      const firstMode = Object.keys(values)[0];
      if (firstMode && values[firstMode]) {
        const color = values[firstMode];
        if (typeof color === 'object' && color.r !== undefined) {
          colors[name] = {
            hex: rgbToHex(color.r, color.g, color.b),
            rgba: `rgba(${Math.round(color.r * 255)}, ${Math.round(color.g * 255)}, ${Math.round(color.b * 255)}, ${color.a || 1})`,
          };
        }
      }
    }
  }
  
  return colors;
}

/**
 * 从样式中提取颜色
 */
function extractColorsFromStyles(styles) {
  const colors = {};
  
  if (!styles || !styles.meta) return colors;
  
  for (const styleId in styles.meta.styles) {
    const style = styles.meta.styles[styleId];
    if (style.styleType === 'FILL') {
      // 需要获取样式的实际值
      const name = style.name.toLowerCase().replace(/[^a-z0-9]/g, '');
      // 注意：样式值需要通过节点获取，这里先记录名称
      colors[name] = { name: style.name, styleId };
    }
  }
  
  return colors;
}

/**
 * 从节点中提取颜色
 */
function extractColorsFromNode(node) {
  const colors = {};
  
  function traverse(n) {
    if (!n) return;
    
    // 检查填充
    if (n.fills && Array.isArray(n.fills)) {
      n.fills.forEach((fill, index) => {
        if (fill.type === 'SOLID' && fill.color) {
          const color = fill.color;
          const name = (n.name || `color${index}`).toLowerCase().replace(/[^a-z0-9]/g, '');
          colors[name] = {
            hex: rgbToHex(color.r, color.g, color.b),
            rgba: `rgba(${Math.round(color.r * 255)}, ${Math.round(color.g * 255)}, ${Math.round(color.b * 255)}, ${fill.opacity || color.a || 1})`,
          };
        }
      });
    }
    
    // 递归子节点
    if (n.children && Array.isArray(n.children)) {
      n.children.forEach(traverse);
    }
  }
  
  traverse(node);
  return colors;
}

/**
 * 提取间距
 */
function extractSpacingFromNode(node) {
  const spacing = {};
  
  function traverse(n) {
    if (!n) return;
    
    if (n.type === 'FRAME' || n.type === 'GROUP') {
      const name = (n.name || '').toLowerCase();
      
      // 检查是否是间距相关的节点
      if (name.includes('spacing') || name.includes('gap') || name.includes('padding') || name.includes('margin')) {
        // 尝试从名称中提取数值
        const match = n.name.match(/(\d+)/);
        if (match) {
          const value = parseFloat(match[1]);
          const key = name.replace(/[^a-z0-9]/g, '');
          spacing[key] = value;
        } else if (n.absoluteBoundingBox) {
          // 使用宽度或高度作为间距值
          const width = n.absoluteBoundingBox.width || 0;
          const height = n.absoluteBoundingBox.height || 0;
          const value = Math.min(width, height) || Math.max(width, height);
          if (value > 0 && value < 100) {
            spacing[name.replace(/[^a-z0-9]/g, '')] = Math.round(value);
          }
        }
      }
    }
    
    if (n.children && Array.isArray(n.children)) {
      n.children.forEach(traverse);
    }
  }
  
  traverse(node);
  return spacing;
}

/**
 * 生成颜色代码（保留现有结构）
 */
function generateColorsCode(colors) {
  if (Object.keys(colors).length === 0) {
    console.warn('⚠️  未找到颜色令牌，将保留现有代码');
    return null;
  }
  
  const lines = [
    "import 'package:flutter/material.dart';",
    "",
    "/// 应用颜色常量",
    "/// 此文件由Figma同步脚本自动生成，请勿手动修改",
    "/// 最后同步时间: " + new Date().toISOString(),
    "class AppColors {",
  ];

  // 主色调
  const primary = colors.primary || colors.primarycolor || colors.p;
  if (primary && primary.hex) {
    lines.push(`  /// 主蓝色: ${primary.hex}`);
    lines.push(`  static const Color primaryColor = Color(0x${hexToInt(primary.hex)});`);
  }
  
  const secondary = colors.secondary || colors.secondarycolor || colors.s;
  if (secondary && secondary.hex) {
    lines.push(`  /// 主紫色: ${secondary.hex}`);
    lines.push(`  static const Color secondaryColor = Color(0x${hexToInt(secondary.hex)});`);
  }

  // 功能性颜色
  if (colors.success && colors.success.hex) {
    lines.push(`  static const Color success = Color(0x${hexToInt(colors.success.hex)});`);
  }
  if (colors.warning && colors.warning.hex) {
    lines.push(`  static const Color warning = Color(0x${hexToInt(colors.warning.hex)});`);
  }
  if (colors.error && colors.error.hex) {
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
  if (Object.keys(spacing).length === 0) {
    console.warn('⚠️  未找到间距令牌，将保留现有代码');
    return null;
  }
  
  const lines = [
    "/// 应用间距常量",
    "/// 此文件由Figma同步脚本自动生成，请勿手动修改",
    "/// 最后同步时间: " + new Date().toISOString(),
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
 * 保存文件（备份原文件）
 */
function saveFile(filePath, content) {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  
  // 备份原文件
  if (fs.existsSync(filePath)) {
    const backupPath = filePath + '.backup.' + Date.now();
    fs.copyFileSync(filePath, backupPath);
    console.log(`📦 已备份原文件: ${backupPath}`);
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

    // 获取变量和样式
    const variables = await getFigmaVariables();
    const styles = await getFigmaStyles();

    // 获取文档节点
    const document = fileData.document;
    
    // 查找设计令牌节点
    let designTokensNode = null;
    if (CONFIG.designTokensNodeId) {
      const nodeData = await figmaRequest(`/files/${CONFIG.fileKey}/nodes?ids=${CONFIG.designTokensNodeId}`);
      designTokensNode = nodeData.nodes[CONFIG.designTokensNodeId];
    } else {
      // 尝试查找设计令牌相关节点
      designTokensNode = findNodeByName({ [document.id]: document }, 'Design Tokens', true) ||
                        findNodeByName({ [document.id]: document }, 'design tokens') ||
                        findNodeByName({ [document.id]: document }, 'tokens');
    }

    // 提取颜色
    console.log('🎨 提取颜色令牌...');
    let allColors = {};
    
    // 从变量中提取
    if (variables) {
      const varColors = extractColorsFromVariables(variables);
      Object.assign(allColors, varColors);
      console.log(`  ✅ 从变量中提取 ${Object.keys(varColors).length} 个颜色`);
    }
    
    // 从样式中提取
    if (styles) {
      const styleColors = extractColorsFromStyles(styles);
      console.log(`  ✅ 从样式中找到 ${Object.keys(styleColors).length} 个颜色样式`);
    }
    
    // 从节点中提取
    if (designTokensNode) {
      const nodeColors = extractColorsFromNode(designTokensNode);
      Object.assign(allColors, nodeColors);
      console.log(`  ✅ 从节点中提取 ${Object.keys(nodeColors).length} 个颜色`);
    }
    
    if (Object.keys(allColors).length > 0) {
      const colorsCode = generateColorsCode(allColors);
      if (colorsCode) {
        saveFile(path.join(CONFIG.outputDir, 'colors/app_colors.dart'), colorsCode);
      }
    } else {
      console.log('⚠️  未找到颜色令牌，跳过颜色同步');
    }

    // 提取间距
    console.log('📏 提取间距令牌...');
    let allSpacing = {};
    
    if (designTokensNode) {
      allSpacing = extractSpacingFromNode(designTokensNode);
    }
    
    if (Object.keys(allSpacing).length > 0) {
      const spacingCode = generateSpacingCode(allSpacing);
      if (spacingCode) {
        saveFile(path.join(CONFIG.outputDir, 'spacing/app_spacing.dart'), spacingCode);
      }
    } else {
      console.log('⚠️  未找到间距令牌，跳过间距同步');
    }

    console.log('\n✨ Figma同步完成！');
    console.log('\n📝 下一步:');
    console.log('1. 检查生成的文件是否符合预期');
    console.log('2. 运行 flutter analyze 检查代码');
    console.log('3. 运行 flutter test 确保测试通过');
    console.log('4. 如有问题，可以使用备份文件恢复');

  } catch (error) {
    console.error('\n❌ 同步失败:', error.message);
    console.log('\n💡 提示:');
    console.log('1. 检查 .env 文件中的配置是否正确');
    console.log('2. 确认 Figma 访问令牌有效');
    console.log('3. 确认文件ID正确且有访问权限');
    process.exit(1);
  }
}

// 运行主函数
if (require.main === module) {
  main();
}

module.exports = { main, figmaRequest, extractColorsFromVariables, extractColorsFromNode };
