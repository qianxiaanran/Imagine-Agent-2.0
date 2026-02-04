// -----------------------------------------------------------------------------
// Audio Processing Utilities (Format Converter)
// -----------------------------------------------------------------------------

// 将 Float32Array 转换为 16-bit PCM (无头信息的纯数据，用于流式传输)
export const floatTo16BitPCM = (input) => {
  const output = new DataView(new ArrayBuffer(input.length * 2));
  for (let i = 0; i < input.length; i++) {
    // 限制范围在 -1 到 1 之间
    let s = Math.max(-1, Math.min(1, input[i]));
    // 转换为 16位 整数
    s = s < 0 ? s * 0x8000 : s * 0x7FFF;
    output.setInt16(i * 2, s, true); // Little Endian
  }
  return output.buffer;
};

// 将 Float32Array 转换为 16-bit PCM WAV Blob (带头信息，用于文件上传)
const encodeWAV = (samples, sampleRate = 16000) => {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeString = (view, offset, string) => {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  };

  const floatTo16BitPCM_Write = (output, offset, input) => {
    for (let i = 0; i < input.length; i++, offset += 2) {
      let s = Math.max(-1, Math.min(1, input[i]));
      s = s < 0 ? s * 0x8000 : s * 0x7FFF;
      output.setInt16(offset, s, true);
    }
  };

  // --- WAV Header (RIFF) ---
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);     // Subchunk1Size
  view.setUint16(20, 1, true);      // AudioFormat (1 = PCM)
  view.setUint16(22, 1, true);      // NumChannels (1 = Mono) 强制单声道
  view.setUint32(24, sampleRate, true); // SampleRate
  view.setUint32(28, sampleRate * 2, true); // ByteRate
  view.setUint16(32, 2, true);      // BlockAlign
  view.setUint16(34, 16, true);     // BitsPerSample
  writeString(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true); // Subchunk2Size

  // --- PCM Data ---
  floatTo16BitPCM_Write(view, 44, samples);

  return new Blob([view], { type: 'audio/wav' });
};

// 核心适配函数：将 MediaRecorder 产生的 WebM blob 转换为后端需要的 16k WAV
export const convertWebMToWav = async (webmBlob) => {
    try {
        const arrayBuffer = await webmBlob.arrayBuffer();
        if (arrayBuffer.byteLength === 0) {
            throw new Error("录音数据为空");
        }

        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

        const TARGET_RATE = 16000;
        const length = Math.ceil(audioBuffer.duration * TARGET_RATE);

        if (length === 0) {
             throw new Error("音频时长过短");
        }

        const offlineContext = new OfflineAudioContext(
            1,
            length,
            TARGET_RATE
        );

        const source = offlineContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(offlineContext.destination);
        source.start();

        const renderedBuffer = await offlineContext.startRendering();

        const wavBlob = encodeWAV(renderedBuffer.getChannelData(0), TARGET_RATE);
        return wavBlob;
    } catch (e) {
        console.error("音频转码失败:", e);
        throw new Error("音频处理失败，请重试");
    }
};