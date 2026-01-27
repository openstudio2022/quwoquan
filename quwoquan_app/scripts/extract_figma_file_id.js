#!/usr/bin/env node

/**
 * 从Figma URL中提取文件ID
 */

const url = process.argv[2];

if (!url) {
  console.log('用法: node scripts/extract_figma_file_id.js <Figma_URL>');
  console.log('');
  console.log('示例:');
  console.log('  node scripts/extract_figma_file_id.js "https://www.figma.com/file/ABC123/File-Name"');
  process.exit(1);
}

// 提取文件ID
const match = url.match(/figma\.com\/(?:file|make)\/([a-zA-Z0-9]+)/);

if (match) {
  const fileId = match[1];
  const isMake = url.includes('/make/');
  
  console.log('📋 URL分析结果:');
  console.log('');
  console.log('文件ID: ' + fileId);
  console.log('URL类型: ' + (isMake ? '社区文件 (/make/)' : '工作区文件 (/file/)'));
  console.log('');
  
  if (isMake) {
    console.log('⚠️  这是社区文件，无法通过API访问');
    console.log('💡 请获取工作区文件的URL（格式: /file/FILE_KEY/File-Name）');
  } else {
    console.log('✅ 这是工作区文件，可以通过API访问');
    console.log('');
    console.log('📝 更新 .env 文件:');
    console.log('FIGMA_FILE_KEY=' + fileId);
  }
} else {
  console.log('❌ 无法从URL中提取文件ID');
  console.log('请确保URL格式正确: https://www.figma.com/file/FILE_KEY/File-Name');
}
