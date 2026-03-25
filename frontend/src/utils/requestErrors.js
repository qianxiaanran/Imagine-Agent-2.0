const readMessage = (error) => String(error?.message || error?.detail || '').trim();

export function getErrorStatus(error) {
  const candidates = [error?.statusCode, error?.status, error?.response?.status];
  for (const candidate of candidates) {
    const numeric = Number(candidate);
    if (Number.isFinite(numeric) && numeric > 0) {
      return numeric;
    }
  }
  return 0;
}

export function isAuthRequiredError(error) {
  const status = getErrorStatus(error);
  const message = readMessage(error).toLowerCase();
  return status === 401 || /not logged in|missing token|invalid session|jwt|登录|认证/.test(message);
}

export function isPermissionDeniedError(error) {
  const status = getErrorStatus(error);
  const message = readMessage(error).toLowerCase();
  return status === 403 || /insufficient permissions|forbidden|无权限|权限不足|account disabled/.test(message);
}

export function getFriendlyRequestError(error, fallback = '请求失败') {
  if (isPermissionDeniedError(error)) {
    return '当前账号无权访问该内容，请联系管理员开通权限。';
  }
  if (isAuthRequiredError(error)) {
    return '登录状态已失效，请重新登录后再试。';
  }
  return readMessage(error) || fallback;
}
