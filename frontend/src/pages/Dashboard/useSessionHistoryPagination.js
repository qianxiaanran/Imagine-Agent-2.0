import { useCallback, useRef } from 'react';
import historyApi from '../../api/history';

export const HISTORY_PAGE_SIZE = 40;

export const normalizeHistoryChatMessages = (messages = []) => {
  const chatMessages = (Array.isArray(messages) ? messages : []).filter(
    (message) => message?.role !== 'context' && message?.role !== 'meta'
  );

  return chatMessages.map((message) => ({
    ...message,
    role: message?.role === 'user' ? 'user' : 'assistant',
    content:
      typeof message?.content === 'string'
        ? message.content
        : message?.content == null
          ? ''
          : JSON.stringify(message.content),
  }));
};

export function useSessionHistoryPagination({
  currentSessionIdRef,
  userId,
  historyCursor,
  historyHasMoreServer,
  chatHistoryLength,
  setChatHistory,
  setVisibleMessageCount,
  setHistoryCursor,
  setHistoryHasMoreServer,
  setIsHistoryPageLoading,
  initialMessageCount,
}) {
  const historyPageLoadPromiseRef = useRef(null);

  const resetHistoryPaginationState = useCallback(() => {
    historyPageLoadPromiseRef.current = null;
    setHistoryCursor(null);
    setHistoryHasMoreServer(false);
    setIsHistoryPageLoading(false);
  }, [setHistoryCursor, setHistoryHasMoreServer, setIsHistoryPageLoading]);

  const loadOlderSessionMessages = useCallback(async () => {
    const sessionId = String(currentSessionIdRef.current || '').trim();
    const uid = String(userId || 'anonymous').trim();
    const beforeId = historyCursor;

    if (!sessionId || !uid || uid === 'anonymous' || !beforeId || !historyHasMoreServer) {
      return [];
    }
    if (historyPageLoadPromiseRef.current) {
      return historyPageLoadPromiseRef.current;
    }

    setIsHistoryPageLoading(true);
    const loadedCountBeforeFetch = chatHistoryLength;
    const requestSessionId = sessionId;

    const request = (async () => {
      try {
        const page = await historyApi.getSessionMessagesPage(sessionId, uid, {
          limit: HISTORY_PAGE_SIZE,
          beforeId,
        });
        if (String(currentSessionIdRef.current || '').trim() !== requestSessionId) {
          return [];
        }

        const olderMessages = normalizeHistoryChatMessages(page.items);
        if (olderMessages.length > 0) {
          setChatHistory((previousMessages) => [...olderMessages, ...previousMessages]);
          setVisibleMessageCount((count) =>
            Math.min(loadedCountBeforeFetch + olderMessages.length, count + initialMessageCount)
          );
        }
        setHistoryCursor(page.nextBeforeId);
        setHistoryHasMoreServer(Boolean(page.hasMore));
        return olderMessages;
      } catch (error) {
        console.error('Failed to load older session messages', error);
        return [];
      } finally {
        historyPageLoadPromiseRef.current = null;
        setIsHistoryPageLoading(false);
      }
    })();

    historyPageLoadPromiseRef.current = request;
    return request;
  }, [
    chatHistoryLength,
    currentSessionIdRef,
    historyCursor,
    historyHasMoreServer,
    initialMessageCount,
    setChatHistory,
    setHistoryCursor,
    setHistoryHasMoreServer,
    setIsHistoryPageLoading,
    setVisibleMessageCount,
    userId,
  ]);

  return {
    loadOlderSessionMessages,
    resetHistoryPaginationState,
  };
}
