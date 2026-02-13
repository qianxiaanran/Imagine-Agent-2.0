// -----------------------------------------------------------------------------
// Audio Processing Utilities (Format Converter)
// -----------------------------------------------------------------------------

// Float32Array -> 16-bit PCM ArrayBuffer (raw PCM, no header)
export const floatTo16BitPCM = (input) => {
  const output = new DataView(new ArrayBuffer(input.length * 2));
  for (let i = 0; i < input.length; i++) {
    let s = Math.max(-1, Math.min(1, input[i]));
    s = s < 0 ? s * 0x8000 : s * 0x7fff;
    output.setInt16(i * 2, s, true);
  }
  return output.buffer;
};

const encodeWAV = (samples, sampleRate = 16000) => {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeString = (dataView, offset, str) => {
    for (let i = 0; i < str.length; i++) {
      dataView.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  const writePCM = (dataView, offset, input) => {
    for (let i = 0; i < input.length; i++, offset += 2) {
      let s = Math.max(-1, Math.min(1, input[i]));
      s = s < 0 ? s * 0x8000 : s * 0x7fff;
      dataView.setInt16(offset, s, true);
    }
  };

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);
  writePCM(view, 44, samples);

  return new Blob([view], { type: 'audio/wav' });
};

const clampSample = (v) => Math.max(-1, Math.min(1, v));

const measureSamples = (samples) => {
  let peak = 0;
  let sumSquares = 0;
  for (let i = 0; i < samples.length; i++) {
    const abs = Math.abs(samples[i]);
    if (abs > peak) peak = abs;
    sumSquares += samples[i] * samples[i];
  }
  const rms = samples.length > 0 ? Math.sqrt(sumSquares / samples.length) : 0;
  return { peak, rms };
};

const trimSilence = (samples, sampleRate, threshold = 0.006, paddingMs = 120) => {
  if (!samples || !samples.length) return samples;

  let start = 0;
  let end = samples.length - 1;

  while (start < samples.length && Math.abs(samples[start]) < threshold) start += 1;
  while (end > start && Math.abs(samples[end]) < threshold) end -= 1;

  if (start >= end) return samples;

  const padding = Math.max(0, Math.floor((paddingMs / 1000) * sampleRate));
  const safeStart = Math.max(0, start - padding);
  const safeEnd = Math.min(samples.length - 1, end + padding);
  return samples.slice(safeStart, safeEnd + 1);
};

const normalizeSamples = (samples) => {
  const { peak, rms } = measureSamples(samples);
  if (peak <= 0) return samples;

  let gainByPeak = 1;
  if (peak < 0.65) {
    gainByPeak = Math.min(6, 0.9 / peak);
  }

  let gainByRms = 1;
  if (rms > 0 && rms < 0.018) {
    gainByRms = Math.min(8, 0.045 / rms);
  }

  const gain = Math.max(gainByPeak, gainByRms);
  if (gain <= 1.05) return samples;

  const out = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    out[i] = clampSample(samples[i] * gain);
  }
  return out;
};

// Convert MediaRecorder blob (webm/mp4) to 16kHz mono WAV for backend ASR
export const convertWebMToWav = async (webmBlob) => {
  try {
    const arrayBuffer = await webmBlob.arrayBuffer();
    if (arrayBuffer.byteLength === 0) {
      throw new Error('录音数据为空');
    }

    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    const audioContext = new AudioContextCtor();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

    const TARGET_RATE = 16000;
    const length = Math.ceil(audioBuffer.duration * TARGET_RATE);
    if (length <= 0) {
      throw new Error('音频时长过短');
    }

    const offlineContext = new OfflineAudioContext(1, length, TARGET_RATE);
    const source = offlineContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(offlineContext.destination);
    source.start();

    const renderedBuffer = await offlineContext.startRendering();
    if (audioContext && audioContext.state !== 'closed') {
      await audioContext.close();
    }

    let mono = renderedBuffer.getChannelData(0);
    mono = trimSilence(mono, TARGET_RATE);
    mono = normalizeSamples(mono);

    const wavBlob = encodeWAV(mono, TARGET_RATE);
    if (wavBlob.size < 3200) {
      throw new Error('音频过短或未采集到有效语音');
    }
    return wavBlob;
  } catch (e) {
    console.error('音频转码失败:', e);
    throw new Error('音频处理失败，请重试');
  }
};
