import apiClient from './apiClient';
import { supabase, STORAGE_BUCKET } from './supabaseClient';
import { v4 as uuidv4 } from 'uuid'; // 如果没有uuid库，可以用简单的随机字符串代替

// 轮询辅助函数 (保持不变)
const pollTaskResult = async (taskId) => {
  const maxRetries = 600;
  let retries = 0;

  while (retries < maxRetries) {
    try {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const response = await apiClient(`/api/voice/result/${taskId}`, { method: 'GET' });

      if (response.status === 'completed') return { text: response.result };
      if (response.status === 'failed') return { text: response.result || '转写失败', error: response.result };
      if (response.status === 'not_found') return { error: '任务丢失' };

      retries++;
    } catch (e) {
      console.error("Polling error", e);
      await new Promise(resolve => setTimeout(resolve, 5000));
      retries++;
    }
  }
  return { error: '等待结果超时' };
};

const voiceApi = {
  /**
   * 上传音频进行转写 (Supabase 存储版)
   * 1. 前端直传 Supabase
   * 2. 后端下载并处理
   */
  transcribe: async (fileOrBlob) => {
    try {
      // --- 步骤 1: 前端直传 Supabase ---
      const fileName = `${Date.now()}_${Math.random().toString(36).substring(7)}.${fileOrBlob.name?.split('.').pop() || 'wav'}`;
      const filePath = `temp/${fileName}`;

      console.log("Creating upload...", filePath);

      const { data, error: uploadError } = await supabase.storage
        .from(STORAGE_BUCKET)
        .upload(filePath, fileOrBlob);

      if (uploadError) {
        console.error("Supabase Upload Error:", uploadError);
        return { error: "文件上传至云存储失败" };
      }

      console.log("Upload success, notifying backend...", data.path);

      // --- 步骤 2: 通知后端处理 (传递 file_path) ---
      // 注意：这里我们不再发送 FormData，而是 JSON
      const submitRes = await apiClient('/api/voice/transcribe_supabase', {
        method: 'POST',
        body: JSON.stringify({
          file_path: data.path, // 传递 Supabase 中的路径
          original_name: fileOrBlob.name || 'recording.wav'
        })
      });

      if (submitRes.error) {
          return { error: submitRes.error };
      }

      const taskId = submitRes.task_id;
      if (!taskId) {
          return { error: "服务器未返回任务ID" };
      }

      console.log("任务已提交，开始轮询结果 ID:", taskId);

      // --- 步骤 3: 轮询结果 ---
      return await pollTaskResult(taskId);

    } catch (e) {
        console.error("Transcribe process failed", e);
        return { error: "请求失败: " + e.message };
    }
  }
};

export default voiceApi;