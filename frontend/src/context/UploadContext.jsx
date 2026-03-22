import { createContext, useContext, useState, useRef, useCallback } from 'react';
import api from '../api/axios';

const UploadContext = createContext(null);

export function useUpload() {
  return useContext(UploadContext);
}

let nextUploadId = 1;

export function UploadProvider({ children }) {
  // uploads: { [id]: { id, filename, uploading, progress, parsedData, error, sourceTest, testName } }
  const [uploads, setUploads] = useState({});
  const abortRefs = useRef({});

  const updateUpload = useCallback((id, patch) => {
    setUploads(prev => ({
      ...prev,
      [id]: { ...prev[id], ...patch },
    }));
  }, []);

  const startUpload = useCallback((file, sourceTest, options = {}) => {
    const id = nextUploadId++;
    const defaultName = sourceTest || file.name.replace(/\.pdf$/i, '');

    setUploads(prev => ({
      ...prev,
      [id]: {
        id,
        filename: file.name,
        uploading: true,
        progress: [{ step: 'uploading', message: 'Uploading PDF to server...' }],
        parsedData: null,
        error: null,
        sourceTest: sourceTest || '',
        testName: defaultName,
      },
    }));

    // Run the SSE upload async
    (async () => {
      const formData = new FormData();
      formData.append('file', file);
      if (sourceTest) formData.append('source_test', sourceTest);
      if (options.sectionsFilter) formData.append('sections_filter', options.sectionsFilter);
      if (options.skipTopics) formData.append('skip_topics', 'true');
      if (options.skipExplanations) formData.append('skip_explanations', 'true');

      const controller = new AbortController();
      abortRefs.current[id] = controller;

      try {
        const token = localStorage.getItem('act_token');
        const response = await fetch(`${api.defaults.baseURL}/admin/upload-pdf`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
          signal: controller.signal,
        });

        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: 'Upload failed' }));
          throw new Error(err.detail || `HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const event = JSON.parse(line.slice(6));
                if (event.step === 'done') {
                  setUploads(prev => {
                    const u = prev[id];
                    if (!u) return prev;
                    return {
                      ...prev,
                      [id]: {
                        ...u,
                        parsedData: event.result,
                        testName: u.testName || event.result?.source_test || '',
                        progress: [...(u.progress || []), { step: 'done', message: event.message }],
                      },
                    };
                  });
                } else {
                  setUploads(prev => {
                    const u = prev[id];
                    if (!u) return prev;
                    return {
                      ...prev,
                      [id]: {
                        ...u,
                        progress: [...(u.progress || []), { step: event.step, message: event.message, ...event }],
                      },
                    };
                  });
                }
              } catch { /* skip malformed */ }
            }
          }
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          updateUpload(id, { error: err.message || 'Upload failed' });
        }
      } finally {
        updateUpload(id, { uploading: false });
        delete abortRefs.current[id];
      }
    })();

    return id;
  }, [updateUpload]);

  const cancelUpload = useCallback((id) => {
    if (abortRefs.current[id]) {
      abortRefs.current[id].abort();
    }
    updateUpload(id, { uploading: false });
  }, [updateUpload]);

  const removeUpload = useCallback((id) => {
    if (abortRefs.current[id]) {
      abortRefs.current[id].abort();
      delete abortRefs.current[id];
    }
    setUploads(prev => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const setParsedData = useCallback((id, updater) => {
    setUploads(prev => {
      const upload = prev[id];
      if (!upload) return prev;
      const newData = typeof updater === 'function' ? updater(upload.parsedData) : updater;
      return { ...prev, [id]: { ...upload, parsedData: newData } };
    });
  }, []);

  // Legacy single-upload compat: check if any upload is active
  const anyUploading = Object.values(uploads).some(u => u.uploading);

  return (
    <UploadContext.Provider value={{
      uploads, anyUploading,
      startUpload, cancelUpload, removeUpload, updateUpload, setParsedData,
    }}>
      {children}
    </UploadContext.Provider>
  );
}
