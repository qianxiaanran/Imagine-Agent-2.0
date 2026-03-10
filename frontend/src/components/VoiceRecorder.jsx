import React, { useState, useEffect, useRef } from 'react';
import { Loader2, Plus, X, Check } from 'lucide-react';
import { convertWebMToWav } from '../utils/audio';

const VoiceRecorder = ({ onCancel, onConfirm }) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const canvasRef = useRef(null);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const animationFrameRef = useRef(null);
  const recordStartAtRef = useRef(0);

  useEffect(() => {
    startRecording();
    return () => stopRecordingCleanup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 48000,
          sampleSize: 16,
          echoCancellation: false,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = stream;

      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContextCtor();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);

      let options = { audioBitsPerSecond: 128000 };
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        options = { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 128000 };
      } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
        options = { mimeType: 'audio/mp4', audioBitsPerSecond: 128000 };
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
      recordStartAtRef.current = Date.now();
      drawWaveform(analyser);
    } catch (err) {
      console.error('Error accessing microphone:', err);
      alert('无法访问麦克风，请检查浏览器权限设置');
      onCancel();
    }
  };

  const stopRecordingCleanup = () => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
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
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  };

  const handleConfirm = () => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      const durationMs = Date.now() - (recordStartAtRef.current || Date.now());
      if (durationMs < 700) {
        alert('录音时间太短，请至少说 1 秒再发送');
        return;
      }

      setIsProcessing(true);
      recorder.onstop = async () => {
        try {
          const rawBlob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });

          if (mediaStreamRef.current) {
            mediaStreamRef.current.getTracks().forEach((track) => track.stop());
            mediaStreamRef.current = null;
          }

          if (rawBlob.size > 0) {
            const wavBlob = await convertWebMToWav(rawBlob);
            onConfirm(wavBlob);
          } else {
            onCancel();
          }
        } catch (error) {
          console.error('Processing failed', error);
          alert('音频处理失败，请重试');
          onCancel();
        } finally {
          stopRecordingCleanup();
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
        const dataIndex = Math.floor((i * (dataArray.length / 2.5)) / barCount);
        const value = dataArray[dataIndex];
        const percent = value / 255;
        const height = Math.max(4, 40 * percent * 1.5);
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
        {isProcessing ? (
          <Loader2 size={22} className="text-gray-300 dark:text-gray-500 animate-spin" />
        ) : (
          <Plus size={22} className="text-gray-300 dark:text-gray-500" />
        )}
      </div>
      <div className="flex-1 flex items-center justify-center relative overflow-hidden h-full">
        <div className="flex-1 h-px border-t-[2px] border-dotted border-gray-300 dark:border-gray-600 mx-1" />
        <div className="flex-shrink-0 mx-2">
          <canvas ref={canvasRef} width={200} height={50} className="block" />
        </div>
        <div className="flex-1 h-px border-t-[2px] border-dotted border-gray-300 dark:border-gray-600 mx-1" />
      </div>
      <div className="flex-shrink-0 flex items-center gap-6 pl-4">
        <button
          onClick={handleCancel}
          className="text-gray-900 dark:text-white hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1"
          title="取消"
          disabled={isProcessing}
        >
          <X size={24} strokeWidth={1.5} />
        </button>
        <button
          onClick={handleConfirm}
          className={`text-gray-900 dark:text-white hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1 ${
            isProcessing ? 'opacity-50 cursor-not-allowed' : ''
          }`}
          title="完成"
          disabled={isProcessing}
        >
          <Check size={24} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
};

export default VoiceRecorder;
