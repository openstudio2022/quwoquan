#!/usr/bin/env node

/**
 * 查找团队中的Figma文件
 * 帮助用户找到工作区中的文件
 */

require('dotenv').config();
const https = require('https');

const CONFIG = {
  apiUrl: 'https://api.figma.com/v1',
  accessToken: process.env.FIGMA_ACCESS_TOKEN,
};

if (!CONFIG.accessToken) {
  console.error('❌ 错误: 未设置 FIGMA_ACCESS_TOKEN');
  process.exit(1);
}

/**
 * 发送API请求
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
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        if (res.statusCode === 200) {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            reject(new Error(`解析JSON失败: ${e.message}`));
          }
        } else {
          const error = JSON.parse(data);
          reject(new Error(`API请求失败: ${res.statusCode} - ${error.err || data}`));
        }
      });
    }).on('error', reject);
  });
}

/**
 * 获取团队列表
 */
async function getTeams() {
  try {
    const data = await figmaRequest('/teams');
    return data.teams || [];
  } catch (error) {
    console.warn('⚠️  获取团队列表失败:', error.message);
    return [];
  }
}

/**
 * 获取团队项目
 */
async function getTeamProjects(teamId) {
  try {
    const data = await figmaRequest(`/teams/${teamId}/projects`);
    return data.projects || [];
  } catch (error) {
    console.warn(`⚠️  获取团队 ${teamId} 的项目失败:`, error.message);
    return [];
  }
}

/**
 * 获取项目文件
 */
async function getProjectFiles(projectId) {
  try {
    const data = await figmaRequest(`/projects/${projectId}/files`);
    return data.files || [];
  } catch (error) {
    console.warn(`⚠️  获取项目 ${projectId} 的文件失败:`, error.message);
    return [];
  }
}

/**
 * 主函数
 */
async function main() {
  console.log('🔍 正在查找工作区中的文件...\n');

  try {
    // 获取团队
    const teams = await getTeams();
    console.log(`找到 ${teams.length} 个团队\n`);

    const allFiles = [];

    // 遍历团队
    for (const team of teams) {
      console.log(`📁 团队: ${team.name} (${team.id})`);
      
      // 获取项目
      const projects = await getTeamProjects(team.id);
      console.log(`   项目数: ${projects.length}`);

      // 遍历项目
      for (const project of projects) {
        console.log(`   📂 项目: ${project.name}`);
        
        // 获取文件
        const files = await getProjectFiles(project.id);
        console.log(`      文件数: ${files.length}`);

        // 查找包含"趣我圈"的文件
        for (const file of files) {
          if (file.name.includes('趣我圈') || file.name.includes('2026')) {
            allFiles.push({
              name: file.name,
              key: file.key,
              lastModified: file.last_modified,
              team: team.name,
              project: project.name,
            });
            console.log(`      ✅ 找到: ${file.name} (ID: ${file.key})`);
          }
        }
      }
      console.log('');
    }

    // 显示结果
    if (allFiles.length > 0) {
      console.log('📋 找到的文件:');
      console.log('');
      allFiles.forEach((file, index) => {
        console.log(`${index + 1}. ${file.name}`);
        console.log(`   文件ID: ${file.key}`);
        console.log(`   团队: ${file.team}`);
        console.log(`   项目: ${file.project}`);
        console.log(`   URL: https://www.figma.com/file/${file.key}/${encodeURIComponent(file.name)}`);
        console.log('');
      });

      // 更新.env文件
      if (allFiles.length === 1) {
        const file = allFiles[0];
        console.log('💡 建议更新 .env 文件:');
        console.log(`FIGMA_FILE_KEY=${file.key}`);
      }
    } else {
      console.log('❌ 未找到包含"趣我圈"或"2026"的文件');
      console.log('');
      console.log('💡 提示:');
      console.log('1. 确认文件已复制到工作区');
      console.log('2. 确认你是团队成员');
      console.log('3. 尝试在Figma界面中手动查找文件');
    }

  } catch (error) {
    console.error('❌ 查找失败:', error.message);
  }
}

main();
