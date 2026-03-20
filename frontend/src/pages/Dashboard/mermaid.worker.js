let mermaidModulePromise;

const loadMermaid = async () => {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import('mermaid').then((module) => module.default || module);
  }
  return mermaidModulePromise;
};

self.onmessage = async (event) => {
  const { requestId, chart, theme = 'default' } = event.data || {};
  if (!requestId || !chart) {
    return;
  }

  try {
    const mermaid = await loadMermaid();
    mermaid.initialize({
      startOnLoad: false,
      theme,
      securityLevel: 'loose',
    });
    const renderId = `mermaid-worker-${requestId}`;
    const { svg } = await mermaid.render(renderId, chart);
    self.postMessage({ requestId, svg });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown mermaid render error';
    self.postMessage({ requestId, error: message });
  }
};
