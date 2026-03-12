import React, { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { ArrowLeft, FileUp, Loader2, RefreshCw, Trash2 } from "lucide-react";
import adminApi from "../../api/admin";
import userApi from "../../api/user";
import presentationApi from "../../api/presentation";

const AuditAdminWorkspace = lazy(() => import("./AuditAdminWorkspace"));

const tabs = [
  { key: "users", label: "用户与权限" },
  { key: "audit", label: "审单后台" },
  { key: "rules", label: "规则库" },
  { key: "kb", label: "知识库治理" },
  { key: "templates", label: "PPT模板导入" },
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
        <div key={`header-${idx}`} className="h-3 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
      ))}
    </div>
    {Array.from({ length: rows }).map((_, rowIdx) => (
      <div
        key={`row-${rowIdx}`}
        className="grid items-center gap-3 border-t border-gray-100 dark:border-gray-800 pt-3"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: columns }).map((_, colIdx) => (
          <div
            key={`cell-${rowIdx}-${colIdx}`}
            className={`h-3 rounded bg-gray-100 dark:bg-gray-800 animate-pulse ${colIdx === 0 ? "w-4/5" : "w-3/4"}`}
          />
        ))}
      </div>
    ))}
  </div>
);

const AdminPanelFallback = ({ text = "加载中..." }) => (
  <div className="rounded-2xl border border-dashed border-gray-200 bg-white/80 px-6 py-16 text-center text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-900/70 dark:text-gray-400">
    {text}
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
      } catch {
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
        className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950"
        style={{ minHeight: 'var(--app-height, 100vh)' }}
      >
        <Loader2 className="animate-spin mr-2" size={18} /> 加载中...
      </div>
    );
  }

  if (!profile || profile.role !== "admin") {
    return (
      <div
        className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center"
        style={{ minHeight: 'var(--app-height, 100vh)' }}
      >
        <div className="bg-white dark:bg-slate-900 rounded-xl shadow border border-gray-200 dark:border-slate-700 p-8 text-center max-w-md">
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">无权限访问</div>
          <div className="text-sm text-gray-500 dark:text-gray-400 mb-6">
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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950" style={{ minHeight: 'var(--app-height, 100vh)' }}>
      <header className="sticky top-0 z-20 bg-white/90 dark:bg-gray-900/90 backdrop-blur border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-[1500px] mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-gray-500 dark:text-gray-400">Admin Console</div>
            <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">企业管理后台</div>
          </div>
          <a
            href="/"
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-800"
          >
            <ArrowLeft size={16} /> 返回工作台
          </a>
        </div>
      </header>

      <div className="max-w-[1500px] mx-auto px-6 py-6">
        <div className="flex flex-wrap gap-2 mb-6">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded-full text-sm font-medium border ${
                activeTab === tab.key
                  ? "bg-black text-white border-black dark:bg-blue-600 dark:border-blue-500"
                  : "bg-white dark:bg-slate-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-slate-700 hover:border-gray-400 dark:hover:border-slate-500"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "users" && <UsersTab currentUserId={profile?.id} />}
        {activeTab === "audit" && (
          <Suspense fallback={<AdminPanelFallback text="正在加载审单后台..." />}>
            <AuditAdminWorkspace />
          </Suspense>
        )}
        {activeTab === "rules" && <RulesTab />}
        {activeTab === "kb" && <KbTab />}
        {activeTab === "templates" && <TemplatesTab />}
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

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminApi.listUsers({ query });
      setUsers(res.data || []);
    } catch {
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

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
    <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 dark:border-slate-700 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800 dark:text-gray-100">用户列表</div>
        <div className="flex items-center gap-2">
          <input
            className="px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
            placeholder="搜索邮箱/手机号/姓名"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            onClick={loadUsers}
            className="px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-slate-800"
          >
            搜索
          </button>
        </div>
      </div>
      <div className="p-4 border-b border-gray-100 dark:border-slate-700 bg-gray-50 dark:bg-slate-950/50">
        <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">添加用户</div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
          <input
            className="px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
            placeholder="账号（邮箱或手机号）"
            value={newUser.account}
            onChange={(e) => setNewUser((prev) => ({ ...prev, account: e.target.value }))}
          />
          <input
            className="px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
            type="password"
            placeholder="密码（至少6位）"
            value={newUser.password}
            onChange={(e) => setNewUser((prev) => ({ ...prev, password: e.target.value }))}
          />
          <input
            className="px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
            placeholder="姓名（可选）"
            value={newUser.name}
            onChange={(e) => setNewUser((prev) => ({ ...prev, name: e.target.value }))}
          />
          <select
            className="px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
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
          <table className="min-w-full text-sm text-gray-700 dark:text-gray-200">
            <thead>
              <tr className="text-left text-gray-500 dark:text-gray-400">
                <th className="py-2">账号</th>
                <th className="py-2">角色</th>
                <th className="py-2">状态</th>
                <th className="py-2">创建时间</th>
                <th className="py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-gray-100 dark:border-gray-800">
                  <td className="py-2">
                    <div className="font-medium text-gray-800 dark:text-gray-100">{u.email || u.phone || u.id}</div>
                    <div className="text-xs text-gray-400">{u.name}</div>
                  </td>
                  <td className="py-2">
                    <select
                      className="border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1 text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200"
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
                      className="border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1 text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200"
                      value={u.status || "active"}
                      onChange={(e) => updateStatus(u.id, e.target.value)}
                    >
                      <option value="active">active</option>
                      <option value="disabled">disabled</option>
                    </select>
                  </td>
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">{u.created_at || "-"}</td>
                  <td className="py-2">
                    <button
                      className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                      onClick={() => forceLogout(u.id)}
                    >
                      强制下线
                    </button>
                    <span className="mx-2 text-gray-300 dark:text-slate-600">|</span>
                    <button
                      className={`text-xs ${u.id === currentUserId ? "text-gray-300 dark:text-slate-600 cursor-not-allowed" : "text-red-600 dark:text-red-400 hover:underline"}`}
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

const RulesTab = () => {
  const [docType, setDocType] = useState("invoice");
  const [rules, setRules] = useState("");
  const [saving, setSaving] = useState(false);

  const loadRules = useCallback(async () => {
    try {
      const res = await adminApi.getAuditRules(docType);
      setRules(JSON.stringify(res.data || [], null, 2));
    } catch {
      setRules("[]");
    }
  }, [docType]);

  useEffect(() => {
    loadRules();
  }, [loadRules]);

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
    <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 dark:border-slate-700 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800 dark:text-gray-100">审单规则库</div>
        <select className="border border-gray-200 dark:border-gray-700 rounded-md px-2 py-1 text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200" value={docType} onChange={(e) => setDocType(e.target.value)}>
          <option value="invoice">invoice</option>
          <option value="contract">contract</option>
          <option value="payment">payment</option>
          <option value="expense">expense</option>
        </select>
      </div>
      <div className="p-4">
        <textarea
          className="w-full min-h-[300px] font-mono text-xs border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
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
    <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 dark:border-slate-700 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800 dark:text-gray-100">知识库治理</div>
        <button className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1" onClick={loadDocs}>
          <RefreshCw size={14} /> 刷新
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        {loading ? (
          <AdminTableSkeleton columns={5} rows={6} />
        ) : (
          <table className="min-w-full text-sm text-gray-700 dark:text-gray-200">
            <thead>
              <tr className="text-left text-gray-500 dark:text-gray-400">
                <th className="py-2">来源</th>
                <th className="py-2">用户</th>
                <th className="py-2">状态</th>
                <th className="py-2">片段数</th>
                <th className="py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={`${d.user_id}-${d.source}`} className="border-t border-gray-100 dark:border-gray-800">
                  <td className="py-2">{d.source}</td>
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">{d.user_id}</td>
                  <td className="py-2">{d.status}</td>
                  <td className="py-2">{d.chunk_count}</td>
                  <td className="py-2 space-x-2">
                    <button className="text-xs text-green-600 dark:text-green-400" onClick={() => updateStatus(d, "approved")}>通过</button>
                    <button className="text-xs text-red-600 dark:text-red-400" onClick={() => updateStatus(d, "rejected")}>拒绝</button>
                    <button className="text-xs text-amber-600 dark:text-amber-400" onClick={() => updateStatus(d, "archived")}>归档</button>
                    <button className="text-xs text-blue-600 dark:text-blue-400" onClick={() => reindexDoc(d)}>重建向量</button>
                    <button className="text-xs text-gray-500 dark:text-gray-400" onClick={() => deleteDoc(d)}>删除</button>
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

const TemplatesTab = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [form, setForm] = useState({
    templateId: "",
    alias: "",
    description: "",
  });

  const loadTemplates = async () => {
    setLoading(true);
    try {
      const res = await presentationApi.listImportedPresentonTemplates();
      setTemplates(Array.isArray(res?.data) ? res.data : []);
    } catch {
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  const handleImportTemplate = async () => {
    const templateId = String(form.templateId || "").trim();
    if (!templateId) {
      window.alert("请输入模板 ID");
      return;
    }
    setImporting(true);
    try {
      await presentationApi.importPresentonTemplate({
        template_id: templateId,
        alias: String(form.alias || "").trim() || undefined,
        description: String(form.description || "").trim() || undefined,
      });
      setForm({ templateId: "", alias: "", description: "" });
      await loadTemplates();
      window.alert("模板导入成功");
    } catch (error) {
      window.alert(error?.message || "模板导入失败");
    } finally {
      setImporting(false);
    }
  };

  const handleDeleteTemplate = async (templateId) => {
    if (!window.confirm(`确认删除模板 ${templateId} 吗？`)) return;
    try {
      await presentationApi.removeImportedPresentonTemplate(templateId);
      await loadTemplates();
    } catch (error) {
      window.alert(error?.message || "删除模板失败");
    }
  };

  return (
    <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 dark:border-slate-700 flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-gray-800 dark:text-gray-100">PPT 模板导入</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            先在 Presenton 按文档流程创建模板，再将模板 ID 导入到本系统。
          </div>
        </div>
        <button className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1" onClick={loadTemplates}>
          <RefreshCw size={14} /> 刷新
        </button>
      </div>

      <div className="p-4 border-b border-gray-100 dark:border-slate-700 bg-gray-50 dark:bg-slate-950/50">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <input
            className="px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
            placeholder="模板ID（必填）"
            value={form.templateId}
            onChange={(e) => setForm((prev) => ({ ...prev, templateId: e.target.value }))}
          />
          <input
            className="px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
            placeholder="模板别名（可选）"
            value={form.alias}
            onChange={(e) => setForm((prev) => ({ ...prev, alias: e.target.value }))}
          />
          <input
            className="px-3 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100"
            placeholder="描述（可选）"
            value={form.description}
            onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
          />
          <button
            onClick={handleImportTemplate}
            disabled={importing}
            className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-black text-white text-sm disabled:opacity-60"
          >
            {importing ? <Loader2 size={14} className="animate-spin" /> : <FileUp size={14} />}
            {importing ? "导入中..." : "导入模板"}
          </button>
        </div>
      </div>

      <div className="p-4 overflow-x-auto">
        {loading ? (
          <AdminTableSkeleton columns={5} rows={5} />
        ) : (
          <table className="min-w-full text-sm text-gray-700 dark:text-gray-200">
            <thead>
              <tr className="text-left text-gray-500 dark:text-gray-400">
                <th className="py-2">模板ID</th>
                <th className="py-2">名称</th>
                <th className="py-2">描述</th>
                <th className="py-2">来源</th>
                <th className="py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {templates.map((template) => (
                <tr key={template.template_id} className="border-t border-gray-100 dark:border-gray-800">
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">{template.template_id}</td>
                  <td className="py-2">{template.name || "-"}</td>
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">{template.description || "-"}</td>
                  <td className="py-2 text-xs">{template.source || "presenton_import"}</td>
                  <td className="py-2">
                    <button
                      className="inline-flex items-center gap-1 text-xs text-red-600 dark:text-red-400 hover:underline"
                      onClick={() => handleDeleteTemplate(template.template_id)}
                    >
                      <Trash2 size={13} /> 删除
                    </button>
                  </td>
                </tr>
              ))}
              {templates.length === 0 && (
                <tr>
                  <td className="py-6 text-center text-sm text-gray-400" colSpan={5}>
                    暂无已导入模板
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
    <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 dark:border-slate-700 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800 dark:text-gray-100">任务中心（审单）</div>
        <button className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1" onClick={loadJobs}>
          <RefreshCw size={14} /> 刷新
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        {loading ? (
          <AdminTableSkeleton columns={5} rows={6} />
        ) : (
          <table className="min-w-full text-sm text-gray-700 dark:text-gray-200">
            <thead>
              <tr className="text-left text-gray-500 dark:text-gray-400">
                <th className="py-2">任务ID</th>
                <th className="py-2">状态</th>
                <th className="py-2">进度</th>
                <th className="py-2">创建时间</th>
                <th className="py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.job_id} className="border-t border-gray-100 dark:border-gray-800">
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">{j.job_id}</td>
                  <td className="py-2">{j.status}</td>
                  <td className="py-2">{j.progress}%</td>
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">{j.created_at}</td>
                  <td className="py-2 space-x-2">
                    <button className="text-xs text-red-600 dark:text-red-400" onClick={() => cancelJob(j.job_id)}>取消</button>
                    <button className="text-xs text-blue-600 dark:text-blue-400" onClick={() => retryJob(j.job_id)}>重试</button>
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
    <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-2xl shadow-sm">
      <div className="p-4 border-b border-gray-100 dark:border-slate-700 flex items-center justify-between">
        <div className="text-sm font-medium text-gray-800 dark:text-gray-100">审计日志</div>
        <button className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1" onClick={loadLogs}>
          <RefreshCw size={14} /> 刷新
        </button>
      </div>
      <div className="p-4 overflow-x-auto">
        {loading ? (
          <AdminTableSkeleton columns={4} rows={6} />
        ) : (
          <table className="min-w-full text-sm text-gray-700 dark:text-gray-200">
            <thead>
              <tr className="text-left text-gray-500 dark:text-gray-400">
                <th className="py-2">时间</th>
                <th className="py-2">管理员</th>
                <th className="py-2">动作</th>
                <th className="py-2">目标</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className="border-t border-gray-100 dark:border-gray-800">
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">{l.created_at}</td>
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">{l.actor_id}</td>
                  <td className="py-2">{l.action}</td>
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">{l.target_id || "-"}</td>
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

