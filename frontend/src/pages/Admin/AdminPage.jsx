import React, { useEffect, useState } from "react";
import { ArrowLeft, Loader2, RefreshCw } from "lucide-react";
import adminApi from "../../api/admin";
import userApi from "../../api/user";

const tabs = [
  { key: "users", label: "用户与权限" },
  { key: "audit", label: "审单记录" },
  { key: "rules", label: "规则库" },
  { key: "kb", label: "知识库治理" },
  { key: "jobs", label: "任务中心" },
  { key: "logs", label: "审计日志" },
];

const AdminTableSkeleton = ({ columns = 5, rows = 6 }) => (
  <div className="space-y-3">
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {Array.from({ length: columns }).map((_, idx) => (
        <div key={`header-${idx}`} className="h-3 rounded bg-gray-200 animate-pulse" />
      ))}
    </div>
    {Array.from({ length: rows }).map((_, rowIdx) => (
      <div
        key={`row-${rowIdx}`}
        className="grid items-center gap-3 border-t border-gray-100 pt-3"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: columns }).map((_, colIdx) => (
          <div
            key={`cell-${rowIdx}-${colIdx}`}
            className={`h-3 rounded bg-gray-100 animate-pulse ${colIdx === 0 ? "w-4/5" : "w-3/4"}`}
          />
        ))}
      </div>
    ))}
  </div>
);

const AdminPage = () => {
  const [profile, setProfile] = useState(null);
  const [activeTab, setActiveTab] = useState("users");
  const [loadingProfile, setLoadingProfile] = useState(true);

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const p = await userApi.getProfile();
        setProfile(p);
      } catch (e) {
        setProfile(null);
      } finally {
        setLoadingProfile(false);
      }
    };
    loadProfile();
  }, []);

  if (loadingProfile) {
    return (
      <div
        className="min-h-screen flex items-center justify-center bg-gray-50"
        style={{ minHeight: 'var(--app-height, 100vh)' }}
      >
        <Loader2 className="animate-spin mr-2" size={18} /> 加载中...
      </div>
    );
  }

  if (!profile || profile.role !== "admin") {
    return (
      <div
        className="min-h-screen bg-gray-50 flex items-center justify-center"
        style={{ minHeight: 'var(--app-height, 100vh)' }}
      >
        <div className="bg-white rounded-xl shadow border border-gray-200 p-8 text-center max-w-md">
          <div className="text-lg font-semibold text-gray-900 mb-2">无权限访问</div>
          <div className="text-sm text-gray-500 mb-6">
            该页面仅管理员可访问。
          </div>
          <a
            href="/"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-black text-white text-sm"
          >
            <ArrowLeft size={16} /> 返回工作台
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50" style={{ minHeight: 'var(--app-height, 100vh)' }}>
      <header className="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-gray-500">Admin Console</div>
            <div className="text-lg font-semibold text-gray-900">企业管理后台</div>
          </div>
          <a
            href="/"
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-100"
          >
            <ArrowLeft size={16} /> 返回工作台
          </a>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-6 py-6">
        <div className="flex flex-wrap gap-2 mb-6">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded-full text-sm font-medium border ${
                activeTab === tab.key
                  ? "bg-black text-white border-black"
                  : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "users" && <UsersTab currentUserId={profile?.id} />}
        {activeTab === "audit" && <AuditTab />}
        {activeTab === "rules" && <RulesTab />}
        {activeTab === "kb" && <KbTab />}
        {activeTab === "jobs" && <JobsTab />}
        {activeTab === "logs" && <LogsTab />}
      </div>
    </div>
  );
};

const UsersTab = ({ currentUserId }) => {
  const [users, setUsers] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newUser, setNewUser] = useState({
    account: "",
    password: "",
    name: "",
    role: "user",
  });

  const loadUsers = async () => {
    setLoading(true);
    try {
      const res = await adminApi.listUsers({ query });
      setUsers(res.data || []);
    } catch (e) {
      setUsers([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const updateRole = async (id, role) => {
    await adminApi.updateUserRole(id, role);
    loadUsers();
  };

  const updateStatus = async (id, status) => {
    await adminApi.updateUserStatus(id, status);
    loadUsers();
  };

  const forceLogout = async (id) => {
    await adminApi.forceLogout(id, "admin_action");
    loadUsers();
  };

  const deleteUser = async (user) => {
    const label = user.email || user.phone || user.id;
    const confirmed = window.confirm(`确认删除用户 ${label} 吗？将同时删除其历史会话与分享记录，且不可恢复。`);
    if (!confirmed) return;
    await adminApi.deleteUser(user.id);
    loadUsers();
  };

  const createUser = async () => {
    const account = (newUser.account || "").trim();
    const password = newUser.password || "";
    const role = newUser.role || "user";
    const name = (newUser.name || "").trim();

    if (!account) {
      window.alert("请输入账号（邮箱或手机号）");
      return;
    }
    if (password.length < 6) {
      window.alert("密码至少 6 位");
      return;
    }

    setCreating(true);
    try {
      await adminApi.createUser({
        account,
        password,
        role,
        name: name || undefined,
      });
      setNewUser({ account: "", password: "", name: "", role: "user" });
      await loadUsers();
      window.alert("用户创建成功");
    } catch (e) {
      window.alert(e?.message || "创建用户失败");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800">用户列表</div>
        <div className="flex items-center gap-2">
          <input
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
            placeholder="搜索邮箱/手机号/姓名"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            onClick={loadUsers}
            className="px-3 py-2 rounded-lg border border-gray-200 text-sm"
          >
            搜索
          </button>
        </div>
      </div>
      <div className="p-4 border-b border-gray-100 bg-gray-50">
        <div className="text-xs text-gray-500 mb-2">添加用户</div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
          <input
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
            placeholder="账号（邮箱或手机号）"
            value={newUser.account}
            onChange={(e) => setNewUser((prev) => ({ ...prev, account: e.target.value }))}
          />
          <input
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
            type="password"
            placeholder="密码（至少6位）"
            value={newUser.password}
            onChange={(e) => setNewUser((prev) => ({ ...prev, password: e.target.value }))}
          />
          <input
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
            placeholder="姓名（可选）"
            value={newUser.name}
            onChange={(e) => setNewUser((prev) => ({ ...prev, name: e.target.value }))}
          />
          <select
            className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
            value={newUser.role}
            onChange={(e) => setNewUser((prev) => ({ ...prev, role: e.target.value }))}
          >
            <option value="user">user</option>
            <option value="admin">admin</option>
            <option value="auditor">auditor</option>
            <option value="kb_admin">kb_admin</option>
          </select>
          <button
            onClick={createUser}
            disabled={creating}
            className="px-3 py-2 rounded-lg bg-black text-white text-sm disabled:opacity-60"
          >
            {creating ? "创建中..." : "创建用户"}
          </button>
        </div>
      </div>
      <div className="p-4 overflow-x-auto">
        {loading ? (
          <AdminTableSkeleton columns={5} rows={6} />
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-2">账号</th>
                <th className="py-2">角色</th>
                <th className="py-2">状态</th>
                <th className="py-2">创建时间</th>
                <th className="py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-gray-100">
                  <td className="py-2">
                    <div className="font-medium text-gray-800">{u.email || u.phone || u.id}</div>
                    <div className="text-xs text-gray-400">{u.name}</div>
                  </td>
                  <td className="py-2">
                    <select
                      className="border border-gray-200 rounded-md px-2 py-1 text-sm"
                      value={u.role || "user"}
                      onChange={(e) => updateRole(u.id, e.target.value)}
                    >
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                      <option value="auditor">auditor</option>
                      <option value="kb_admin">kb_admin</option>
                    </select>
                  </td>
                  <td className="py-2">
                    <select
                      className="border border-gray-200 rounded-md px-2 py-1 text-sm"
                      value={u.status || "active"}
                      onChange={(e) => updateStatus(u.id, e.target.value)}
                    >
                      <option value="active">active</option>
                      <option value="disabled">disabled</option>
                    </select>
                  </td>
                  <td className="py-2 text-xs text-gray-500">{u.created_at || "-"}</td>
                  <td className="py-2">
                    <button
                      className="text-xs text-blue-600 hover:underline"
                      onClick={() => forceLogout(u.id)}
                    >
                      强制下线
                    </button>
                    <span className="mx-2 text-gray-300">|</span>
                    <button
                      className={`text-xs ${u.id === currentUserId ? "text-gray-300 cursor-not-allowed" : "text-red-600 hover:underline"}`}
                      onClick={() => deleteUser(u)}
                      disabled={u.id === currentUserId}
                      title={u.id === currentUserId ? "无法删除当前账号" : "删除用户"}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td className="py-6 text-center text-sm text-gray-400" colSpan={5}>
                    暂无用户
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

const AuditTab = () => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [risk, setRisk] = useState("");

  const loadRecords = async () => {
    setLoading(true);
    try {
      const res = await adminApi.listAuditRecords({ status, risk_level: risk });
      setRecords(res.data || []);
    } catch {
      setRecords([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRecords();
  }, []);

  const review = async (jobId, reviewStatus) => {
    await adminApi.reviewAudit({ job_id: jobId, status: reviewStatus });
    loadRecords();
  };

  return (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800">审单记录</div>
        <div className="flex items-center gap-2">
          <select className="border border-gray-200 rounded-md px-2 py-1 text-sm" value={risk} onChange={(e) => setRisk(e.target.value)}>
            <option value="">风险等级</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
          <select className="border border-gray-200 rounded-md px-2 py-1 text-sm" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">状态</option>
            <option value="done">done</option>
            <option value="failed">failed</option>
            <option value="running">running</option>
          </select>
          <button className="px-3 py-2 rounded-lg border border-gray-200 text-sm" onClick={loadRecords}>
            筛选
          </button>
        </div>
      </div>
      <div className="p-4 overflow-x-auto">
        {loading ? (
          <AdminTableSkeleton columns={6} rows={6} />
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-2">任务ID</th>
                <th className="py-2">用户</th>
                <th className="py-2">类型</th>
                <th className="py-2">风险</th>
                <th className="py-2">摘要</th>
                <th className="py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.job_id} className="border-t border-gray-100">
                  <td className="py-2 text-xs text-gray-500">{r.job_id}</td>
                  <td className="py-2 text-xs text-gray-500">{r.user_id}</td>
                  <td className="py-2">{r.doc_type}</td>
                  <td className="py-2">{r.risk_level || "-"}</td>
                  <td className="py-2 text-xs text-gray-500">{r.summary || "-"}</td>
                  <td className="py-2 space-x-2">
                    <button className="text-xs text-green-600" onClick={() => review(r.job_id, "approved")}>通过</button>
                    <button className="text-xs text-red-600" onClick={() => review(r.job_id, "rejected")}>驳回</button>
                    <button className="text-xs text-amber-600" onClick={() => review(r.job_id, "need_more")}>补材料</button>
                  </td>
                </tr>
              ))}
              {records.length === 0 && (
                <tr>
                  <td className="py-6 text-center text-sm text-gray-400" colSpan={6}>
                    暂无记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

const RulesTab = () => {
  const [docType, setDocType] = useState("invoice");
  const [rules, setRules] = useState("");
  const [saving, setSaving] = useState(false);

  const loadRules = async () => {
    try {
      const res = await adminApi.getAuditRules(docType);
      setRules(JSON.stringify(res.data || [], null, 2));
    } catch {
      setRules("[]");
    }
  };

  useEffect(() => {
    loadRules();
  }, [docType]);

  const saveRules = async () => {
    setSaving(true);
    try {
      const parsed = JSON.parse(rules || "[]");
      await adminApi.updateAuditRules(docType, parsed);
      alert("规则已更新");
    } catch (e) {
      alert(e?.message || "规则更新失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800">审单规则库</div>
        <select className="border border-gray-200 rounded-md px-2 py-1 text-sm" value={docType} onChange={(e) => setDocType(e.target.value)}>
          <option value="invoice">invoice</option>
          <option value="contract">contract</option>
          <option value="payment">payment</option>
          <option value="expense">expense</option>
        </select>
      </div>
      <div className="p-4">
        <textarea
          className="w-full min-h-[300px] font-mono text-xs border border-gray-200 rounded-lg p-3"
          value={rules}
          onChange={(e) => setRules(e.target.value)}
        />
        <div className="mt-3">
          <button
            onClick={saveRules}
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-black text-white text-sm"
          >
            {saving ? "保存中..." : "保存规则"}
          </button>
        </div>
      </div>
    </div>
  );
};

const KbTab = () => {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadDocs = async () => {
    setLoading(true);
    try {
      const res = await adminApi.listKbDocuments();
      setDocs(res.data || []);
    } catch {
      setDocs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocs();
  }, []);

  const updateStatus = async (item, status) => {
    await adminApi.updateKbStatus({ source: item.source, user_id: item.user_id, status });
    loadDocs();
  };

  const deleteDoc = async (item) => {
    await adminApi.deleteKbDocument({ source: item.source, user_id: item.user_id });
    loadDocs();
  };

  const reindexDoc = async (item) => {
    await adminApi.reindexKbDocument({ source: item.source, user_id: item.user_id });
    loadDocs();
  };

  return (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800">知识库治理</div>
        <button className="text-sm text-gray-500 flex items-center gap-1" onClick={loadDocs}>
          <RefreshCw size={14} /> 刷新
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        {loading ? (
          <AdminTableSkeleton columns={5} rows={6} />
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-2">来源</th>
                <th className="py-2">用户</th>
                <th className="py-2">状态</th>
                <th className="py-2">片段数</th>
                <th className="py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={`${d.user_id}-${d.source}`} className="border-t border-gray-100">
                  <td className="py-2">{d.source}</td>
                  <td className="py-2 text-xs text-gray-500">{d.user_id}</td>
                  <td className="py-2">{d.status}</td>
                  <td className="py-2">{d.chunk_count}</td>
                  <td className="py-2 space-x-2">
                    <button className="text-xs text-green-600" onClick={() => updateStatus(d, "approved")}>通过</button>
                    <button className="text-xs text-red-600" onClick={() => updateStatus(d, "rejected")}>拒绝</button>
                    <button className="text-xs text-amber-600" onClick={() => updateStatus(d, "archived")}>归档</button>
                    <button className="text-xs text-blue-600" onClick={() => reindexDoc(d)}>重建向量</button>
                    <button className="text-xs text-gray-500" onClick={() => deleteDoc(d)}>删除</button>
                  </td>
                </tr>
              ))}
              {docs.length === 0 && (
                <tr>
                  <td className="py-6 text-center text-sm text-gray-400" colSpan={5}>
                    暂无文档
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

const JobsTab = () => {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadJobs = async () => {
    setLoading(true);
    try {
      const res = await adminApi.listJobs({ job_type: "audit" });
      setJobs(res.data || []);
    } catch {
      setJobs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadJobs();
  }, []);

  const cancelJob = async (jobId) => {
    await adminApi.cancelJob(jobId);
    loadJobs();
  };

  const retryJob = async (jobId) => {
    await adminApi.retryJob(jobId);
    loadJobs();
  };

  return (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800">任务中心（审单）</div>
        <button className="text-sm text-gray-500 flex items-center gap-1" onClick={loadJobs}>
          <RefreshCw size={14} /> 刷新
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        {loading ? (
          <AdminTableSkeleton columns={5} rows={6} />
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-2">任务ID</th>
                <th className="py-2">状态</th>
                <th className="py-2">进度</th>
                <th className="py-2">创建时间</th>
                <th className="py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id} className="border-t border-gray-100">
                  <td className="py-2 text-xs text-gray-500">{j.job_id}</td>
                  <td className="py-2">{j.status}</td>
                  <td className="py-2">{j.progress}%</td>
                  <td className="py-2 text-xs text-gray-500">{j.created_at}</td>
                  <td className="py-2 space-x-2">
                    <button className="text-xs text-red-600" onClick={() => cancelJob(j.job_id)}>取消</button>
                    <button className="text-xs text-blue-600" onClick={() => retryJob(j.job_id)}>重试</button>
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td className="py-6 text-center text-sm text-gray-400" colSpan={5}>
                    暂无任务
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

const LogsTab = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const res = await adminApi.listAdminLogs();
      setLogs(res.data || []);
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  return (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800">审计日志</div>
        <button className="text-sm text-gray-500 flex items-center gap-1" onClick={loadLogs}>
          <RefreshCw size={14} /> 刷新
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        {loading ? (
          <AdminTableSkeleton columns={4} rows={6} />
        ) : (
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-2">时间</th>
                <th className="py-2">管理员</th>
                <th className="py-2">动作</th>
                <th className="py-2">目标</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className="border-t border-gray-100">
                  <td className="py-2 text-xs text-gray-500">{l.created_at}</td>
                  <td className="py-2 text-xs text-gray-500">{l.actor_id}</td>
                  <td className="py-2">{l.action}</td>
                  <td className="py-2 text-xs text-gray-500">{l.target_id || "-"}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td className="py-6 text-center text-sm text-gray-400" colSpan={4}>
                    暂无日志
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default AdminPage;

