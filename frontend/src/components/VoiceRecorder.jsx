import React, { useState, useEffect, useRef } from 'react';
import { Loader2, Plus, X, Check } from 'lucide-react';
// 注意：请确保 convertWebMToWav 内部会将音频重采样(Resample)到 16000Hz
import { convertWebMToWav } from '../utils/audio';

const VoiceRecorder = ({ onCancel, onConfirm }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const canvasRef = useRef(null);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const animationFrameRef = useRef(null);

  useEffect(() => {
    startRecording();
    return () => stopRecordingCleanup();
  }, []);

  const startRecording = async () => {
    try {
      // 关键修改：强制请求 16kHz 单声道，匹配百度 API 要求
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,       // 强制单声道
          sampleRate: 16000,     // 尝试请求 16kHz (部分浏览器可能忽略)
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      mediaStreamRef.current = stream;

      // 音频可视化上下文
      const audioContext = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: 16000 // 尝试设置上下文采样率
      });
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);

      // 选择录音格式：优先 WebM Opus
      let options = {};
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        options = { mimeType: 'audio/webm;codecs=opus' };
      } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
        options = { mimeType: 'audio/mp4' };
      }

      const mediaRecorder = new MediaRecorder(stream, options);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
      drawWaveform(analyser);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      alert("无法访问麦克风，请检查权限设置");
      onCancel();
    }
  };

  const stopRecordingCleanup = () => {
    if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
    }
    if (audioContextRef.current) {
        if (audioContextRef.current.state !== 'closed') {
            audioContextRef.current.close();
        }
        audioContextRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
    }
    if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
        mediaStreamRef.current = null;
    }
    setIsRecording(false);
  };

  const handleConfirm = () => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
        setIsProcessing(true);

        // 我们手动停止 recorder，触发 onstop 事件处理逻辑
        // 注意：不要在 recorder.stop() 之前定义 onstop，防止多次绑定或闭包问题
        recorder.onstop = async () => {
            try {
                // 1. 生成原始 Blob (通常是 WebM 或 MP4)
                const webmBlob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });

                // 2. 清理资源
                if (mediaStreamRef.current) {
                    mediaStreamRef.current.getTracks().forEach(track => track.stop());
                    mediaStreamRef.current = null;
                }

                if (webmBlob.size > 0) {
                    // 3. 转换为 WAV (必须确保转换为 16000Hz, 16bit, Mono)
                    // 如果 convertWebMToWav 只是简单封装头信息而不重采样，
                    // 且录音是 48k，发给百度(设置了rate=16k)会导致声音变慢/无法识别。
                    const wavBlob = await convertWebMToWav(webmBlob);
                    onConfirm(wavBlob);
                } else {
                    onCancel();
                }
            } catch (error) {
                console.error("Processing failed", error);
                alert("音频处理失败");
                onCancel();
            } finally {
                stopRecordingCleanup(); // 确保彻底清理
                setIsProcessing(false);
            }
        };
        recorder.stop();
    } else {
        stopRecordingCleanup();
        onCancel();
    }
  };

  const handleCancel = () => {
      stopRecordingCleanup();
      onCancel();
  };

  const drawWaveform = (analyser) => {
    if (!canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const render = () => {
        if (!canvasRef.current) return;
        animationFrameRef.current = requestAnimationFrame(render);
        analyser.getByteFrequencyData(dataArray);

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const barCount = 20;
        const barWidth = 4;
        const gap = 6;
        const totalWidth = barCount * (barWidth + gap) - gap;
        const startX = (canvas.width - totalWidth) / 2;
        const centerY = canvas.height / 2;

        const isDark = document.documentElement.classList.contains('dark');
        ctx.fillStyle = isDark ? '#ffffff' : '#000000';

        for (let i = 0; i < barCount; i++) {
            const dataIndex = Math.floor(i * (dataArray.length / 2.5) / barCount);
            let value = dataArray[dataIndex];
            const percent = value / 255;
            let height = Math.max(4, 40 * percent * 1.5);
            const x = startX + i * (barWidth + gap);
            const y = centerY - height / 2;
            ctx.beginPath();
            ctx.roundRect(x, y, barWidth, height, 10);
            ctx.fill();
        }
    };
    render();
  };

  return (
    <div className="flex items-center w-full h-full bg-white dark:bg-gray-800 rounded-full px-5 shadow-[0_2px_15px_-3px_rgba(0,0,0,0.1),0_10px_20px_-2px_rgba(0,0,0,0.04)] border border-gray-200 dark:border-gray-700 animate-in fade-in zoom-in duration-200">
      <div className="flex-shrink-0 pr-4">
        {isProcessing ? <Loader2 size={22} className="text-gray-300 dark:text-gray-500 animate-spin" /> : <Plus size={22} className="text-gray-300 dark:text-gray-500" />}
      </div>
      <div className="flex-1 flex items-center justify-center relative overflow-hidden h-full">
         <div className="flex-1 h-px border-t-[2px] border-dotted border-gray-300 dark:border-gray-600 mx-1"></div>
         <div className="flex-shrink-0 mx-2">
            <canvas ref={canvasRef} width={200} height={50} className="block" />
         </div>
         <div className="flex-1 h-px border-t-[2px] border-dotted border-gray-300 dark:border-gray-600 mx-1"></div>
      </div>
      <div className="flex-shrink-0 flex items-center gap-6 pl-4">
          <button onClick={handleCancel} className="text-gray-900 dark:text-white hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1" title="取消" disabled={isProcessing}><X size={24} strokeWidth={1.5} /></button>
          <button onClick={handleConfirm} className={`text-gray-900 dark:text-white hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1 ${isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`} title="完成" disabled={isProcessing}><Check size={24} strokeWidth={1.5} /></button>
      </div>

    </div>
  );
};

export default VoiceRecorder;