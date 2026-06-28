import React, { useState, useMemo, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Activity, Bell, CheckCircle2, CircleDollarSign, Clock3,
  ExternalLink, ListChecks, MessageCircle, Moon, PackageOpen,
  Plus, RefreshCw, Search, Settings, Sparkles, Sun,
  Tag, Trash2, Zap,
} from "lucide-react";

import {
  useSchemes, useMonitorStatus, useSystemInfo, useSchemeDetail,
  useWechatStatus, useCreateScheme, useUpdateScheme, useDeleteScheme,
  useAddKeyword, useUpdateKeyword, useDeleteKeyword, useRestartScheme,
  useTestWebhook, useTestWechat, useGlobalSettings,
} from "@/helpers/api";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  SidebarProvider, Sidebar, SidebarHeader, SidebarContent,
  SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarGroupAction, SidebarGroupContent,
  SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarMenuAction,
  SidebarMenuBadge, SidebarInset, SidebarTrigger,
} from "@/components/ui/sidebar";
import SchemeModal from "@/components/modals/SchemeModal";
import KeywordModal from "@/components/modals/KeywordModal";
import SettingsModal from "@/components/modals/SettingsModal";
import WechatModal from "@/components/modals/WechatModal";
import DingtalkModal from "@/components/modals/DingtalkModal";

const STATUS_LABELS = {
  online: "在线", connecting: "连接中", reconnecting: "重连中",
  session_expired: "会话过期", error: "异常", stopped: "已停止",
};

function moneyRange(keyword) {
  if (!keyword) return "不限";
  if ((keyword.price_min || 0) <= 0 && Number(keyword.price_max) >= 999999) return "不限价格";
  return `¥${keyword.price_min || 0} - ¥${keyword.price_max || 999999}`;
}

function stripTags(value = "") {
  return String(value).replace(/<[^>]+>/g, "").trim();
}

/* ---------- AppSidebar ---------- */
function AppSidebar({ schemes, status, selectedId, onSelect, onToggle, onNewScheme }) {
  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-green-500 text-white shadow-md group-data-[collapsible=icon]:size-7">
            <Sparkles size={18} className="group-data-[collapsible=icon]:size-4" />
          </div>
          <div className="flex flex-col group-data-[collapsible=icon]:hidden">
            <strong className="text-sm">SMZDM Monitor</strong>
            <span className="text-xs text-muted-foreground">好价监控桌面版</span>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>
            <span className="flex items-center gap-1.5">
              <Search size={14} />
              {schemes.length ? `${schemes.length} 个方案` : "暂无方案"}
            </span>
          </SidebarGroupLabel>
          <SidebarGroupAction onClick={onNewScheme} title="新建方案">
            <Plus size={16} />
            <span className="sr-only">新建方案</span>
          </SidebarGroupAction>
          <SidebarGroupContent>
            <SidebarMenu>
              {schemes.map((scheme) => {
                const runtimeScheme = status.schemes?.find((item) => item.id === scheme.id);
                const isRunning = runtimeScheme?.is_running;
                return (
                  <SidebarMenuItem key={scheme.id}>
                    <SidebarMenuButton
                      isActive={selectedId === scheme.id}
                      onClick={() => onSelect(scheme.id)}
                      tooltip={scheme.name}
                      className="h-12"
                    >
                      <span className={`flex size-2 shrink-0 rounded-full ${
                        isRunning ? "bg-green-500 shadow-[0_0_0_3px_rgba(34,197,94,0.2)]" :
                        scheme.is_active ? "bg-amber-500" : "bg-muted-foreground/40"
                      }`} />
                      <span className="flex flex-1 flex-col overflow-hidden">
                        <span className="truncate font-medium">{scheme.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {isRunning ? "监控中" : scheme.is_active ? "已启用" : "已停用"} · {scheme.refresh_interval}s
                        </span>
                      </span>
                    </SidebarMenuButton>
                    <SidebarMenuAction
                      onClick={(e) => { e.stopPropagation(); onToggle(scheme); }}
                      showOnHover
                      title={scheme.is_active ? "停用" : "启用"}
                    >
                      <Switch
                        checked={Boolean(scheme.is_active)}
                        className="scale-75"
                        onCheckedChange={() => onToggle(scheme)}
                      />
                    </SidebarMenuAction>
                    {runtimeScheme?.notification_stats?.success > 0 && (
                      <SidebarMenuBadge>
                        {runtimeScheme.notification_stats.success}
                      </SidebarMenuBadge>
                    )}
                  </SidebarMenuItem>
                );
              })}
              {!schemes.length && (
                <div className="flex flex-col items-center gap-2 p-4 text-center text-muted-foreground">
                  <PackageOpen size={24} />
                  <span className="text-xs">创建第一个方案开始监控</span>
                </div>
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <div className="flex items-center justify-between gap-2 rounded-md px-2 py-1 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
          <span className="flex items-center gap-1">
            <Activity size={14} className={status.running ? "text-green-500" : "text-muted-foreground/50"} />
            {status.running_tasks ? `${status.running_tasks} 运行中` : "空闲"}
          </span>
          <span className="flex items-center gap-1">
            <Clock3 size={14} />
            15s 轮询
          </span>
        </div>
      </SidebarFooter>

    </Sidebar>
  );
}

/* ---------- MetricCard ---------- */
function MetricCard({ label, value, icon: Icon, color }) {
  return (
    <Card className="relative overflow-hidden">
      <CardContent className="flex items-center gap-3 p-4">
        <div className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${color || "bg-primary/10 text-primary"}`}>
          <Icon size={20} />
        </div>
        <div className="flex flex-col">
          <strong className="text-2xl font-bold tabular-nums">{value}</strong>
          <span className="text-xs text-muted-foreground">{label}</span>
        </div>
      </CardContent>
    </Card>
  );
}

/* ---------- ProductRow ---------- */
function ProductRow({ product }) {
  return (
    <a
      href={product.article_url || "#"}
      target="_blank"
      rel="noreferrer"
      className="group/prod flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/20 p-3 no-underline transition-colors hover:bg-muted/40 hover:border-primary/30"
    >
      <div className="min-w-0 flex-1">
        <strong className="block truncate text-sm group-hover/prod:text-primary transition-colors">
          {product.article_title}
        </strong>
        <span className="text-xs text-muted-foreground">
          {product.keyword} · {product.article_mall || "未知商城"} · {product.article_date || "未知时间"}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="font-bold text-rose-400 text-sm">{stripTags(product.article_price || "价格未知")}</span>
        {product.article_url && <ExternalLink size={14} className="text-muted-foreground group-hover/prod:text-primary transition-colors" />}
      </div>
    </a>
  );
}

/* ---------- KeywordRow ---------- */
function KeywordRow({ keyword, onEdit, onDelete }) {
  return (
    <div className="group/kw flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/20 p-3 transition-colors hover:bg-muted/40">
      <div className="min-w-0 flex-1">
        <strong className="block truncate text-sm">{keyword.keyword}</strong>
        <span className="text-xs text-muted-foreground">
          {keyword.order_type} · {moneyRange(keyword)}
        </span>
      </div>
      <div className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover/kw:opacity-100">
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => onEdit(keyword)}>编辑</Button>
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-destructive" onClick={() => onDelete(keyword.id)}>删除</Button>
      </div>
    </div>
  );
}

/* ---------- DetailView ---------- */
function DetailView({ detail, selectedRuntime, wechatAccounts, globalWebhook, onEdit, onToggle, onRestart, onDelete,
  onAddKeyword, onEditKeyword, onDeleteKeyword, onTestWebhook, onTestWechat, onOpenWechat }) {
  return (
    <div className="flex flex-col gap-4">
      {/* Hero */}
      <Card className="relative overflow-hidden border bg-gradient-to-br from-primary/10 via-muted/50 to-muted">
        <div className="absolute right-0 top-0 h-32 w-32 rounded-full bg-primary/5 blur-3xl" />
        <CardContent className="relative flex flex-wrap items-center justify-between gap-4 p-6">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Badge variant={selectedRuntime?.is_running ? "success" : detail.is_active ? "warning" : "secondary"}>
                {selectedRuntime?.is_running ? "正在监控" : detail.is_active ? "已启用" : "已停用"}
              </Badge>
              {selectedRuntime?.is_running && (
                <span className="flex items-center gap-1 text-xs text-green-500">
                  <Zap size={12} /> 实时
                </span>
              )}
            </div>
            <h2 className="text-2xl font-bold">{detail.name}</h2>
            <p className="text-sm text-muted-foreground">
              {detail.keywords?.length || 0} 个关键词 · {detail.refresh_interval}s 刷新 ·
              今日通知 {detail.notification_stats?.success || 0} 条
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant={detail.is_active ? "default" : "outline"}
              onClick={() => onToggle(detail)}
            >
              {detail.is_active ? "启用中" : "已停用"}
            </Button>
            <Button variant="outline" onClick={() => onEdit(detail)}>编辑</Button>
            <Button variant="outline" onClick={() => onRestart(detail.id)}>
              <RefreshCw size={16} /> 重启
            </Button>
            <Button variant="destructive" onClick={() => onDelete(detail.id)}>
              <Trash2 size={16} /> 删除
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Keywords */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
            <div>
              <CardTitle className="text-base">关键词</CardTitle>
              <CardDescription>{detail.keywords?.length || 0} 个启用关键词</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={onAddKeyword}>
              <Plus size={14} /> 添加
            </Button>
          </CardHeader>
          <CardContent className="flex max-h-[400px] flex-col gap-2 overflow-auto pt-0">
            {(detail.keywords || []).map((kw) => (
              <KeywordRow key={kw.id} keyword={kw} onEdit={onEditKeyword} onDelete={onDeleteKeyword} />
            ))}
            {!detail.keywords?.length && (
              <div className="flex flex-col items-center gap-2 p-8 text-center text-muted-foreground">
                <PackageOpen size={24} />
                <span className="text-sm">还没有关键词，添加一个商品词开始监控</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Products */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">最近发现</CardTitle>
            <CardDescription>最多显示 50 条历史商品</CardDescription>
          </CardHeader>
          <CardContent className="flex max-h-[400px] flex-col gap-2 overflow-auto pt-0">
            {(detail.recent_products || []).map((product) => (
              <ProductRow key={product.id} product={product} />
            ))}
            {!detail.recent_products?.length && (
              <div className="flex flex-col items-center gap-2 p-8 text-center text-muted-foreground">
                <PackageOpen size={24} />
                <span className="text-sm">暂无商品记录，监控发现新品后会出现在这里</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Notification panel */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
          <div>
            <CardTitle className="text-base">通知配置</CardTitle>
            <CardDescription>今日成功 {detail.notification_stats?.success || 0} 条</CardDescription>
          </div>
          <Bell size={18} className="text-muted-foreground" />
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className={`flex size-2.5 rounded-full ${(detail.dingtalk_webhook || globalWebhook) ? "bg-green-500" : "bg-muted-foreground/40"}`} />
              <span className="text-sm">{(detail.dingtalk_webhook || globalWebhook) ? (detail.dingtalk_webhook ? "已配置自定义钉钉" : "已启用全局钉钉") : "未配置钉钉"}</span>
            </div>
            {(detail.dingtalk_webhook || globalWebhook) && (
              <Button variant="outline" size="sm" onClick={() => onTestWebhook(detail)}>发送测试通知</Button>
            )}
            <Separator orientation="vertical" className="h-6" />
            <div className="flex items-center gap-2">
              <span className={`flex size-2.5 rounded-full ${detail.wechat_enabled ? "bg-green-500" : "bg-muted-foreground/40"}`} />
              <span className="text-sm">{detail.wechat_enabled ? "微信通知已启用" : "微信未启用"}</span>
            </div>
            {detail.wechat_enabled && (() => {
              const bound = wechatAccounts[0];
              if (bound && bound.status && bound.status !== "online") {
                return (
                  <span className="text-sm text-destructive">
                    ⚠️ {STATUS_LABELS[bound.status] || bound.status}
                    {bound.last_error ? ` - ${bound.last_error}` : ""}
                  </span>
                );
              }
              return null;
            })()}
            {detail.wechat_enabled && (
              <Button variant="outline" size="sm" onClick={() => onTestWechat(detail)}>测试微信</Button>
            )}
            <Button variant="outline" size="sm" onClick={onOpenWechat}>
              <MessageCircle size={14} /> 绑定微信
            </Button>
            <Separator orientation="vertical" className="h-6" />
            <div className="flex items-center gap-2">
              <span className={`flex size-2.5 rounded-full ${detail.wxpusher_enabled ? "bg-green-500" : "bg-muted-foreground/40"}`} />
              <span className="text-sm">{detail.wxpusher_enabled ? "WxPusher 已启用" : "WxPusher 未启用"}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ---------- WelcomeView ---------- */
function WelcomeView({ onNewScheme }) {
  return (
    <div className="flex min-h-[500px] flex-col items-center justify-center gap-6 text-center">
      <div className="flex size-20 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-green-500 text-white shadow-xl">
        <Sparkles size={36} />
      </div>
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold">准备好开始监控好价</h2>
        <p className="max-w-md text-muted-foreground">
          创建方案、添加关键词，软件会在后台常驻托盘并自动检查新品。
        </p>
      </div>
      <Button size="lg" onClick={onNewScheme}>
        <Plus size={18} /> 创建监控方案
      </Button>
    </div>
  );
}

/* ---------- DetailSkeleton ---------- */
function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="p-6">
          <Skeleton className="mb-3 h-6 w-24" />
          <Skeleton className="mb-2 h-8 w-48" />
          <Skeleton className="h-4 w-64" />
        </CardContent>
      </Card>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="pb-3">
              <Skeleton className="h-5 w-20" />
              <Skeleton className="h-4 w-32" />
            </CardHeader>
            <CardContent className="flex flex-col gap-2 pt-0">
              {Array.from({ length: 3 }).map((_, j) => (
                <Skeleton key={j} className="h-14 w-full" />
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ---------- Main App ---------- */
export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [selectedId, setSelectedId] = useState(null);
  const [modal, setModal] = useState(null);
  const [appInfo, setAppInfo] = useState(null);

  const qc = useQueryClient();

  const { data: schemes = [], isLoading: schemesLoading } = useSchemes();
  const { data: status = { running: false, running_tasks: 0, active_schemes: 0, schemes: [] } } = useMonitorStatus();
  const { data: system } = useSystemInfo();
  const { data: detail, isLoading: detailLoading } = useSchemeDetail(selectedId);
  const { data: wechatData = { status: null, accounts: [], conversations: [] } } = useWechatStatus();
  const { data: globalSettings } = useGlobalSettings();
  const globalWebhook = globalSettings?.dingtalk_webhook?.value || "";
  const globalSecret = globalSettings?.dingtalk_secret?.value || "";

  const createSchemeMut = useCreateScheme();
  const updateSchemeMut = useUpdateScheme();
  const deleteSchemeMut = useDeleteScheme();
  const addKeywordMut = useAddKeyword(selectedId);
  const updateKeywordMut = useUpdateKeyword(selectedId);
  const deleteKeywordMut = useDeleteKeyword(selectedId);
  const restartSchemeMut = useRestartScheme();
  const testWebhookMut = useTestWebhook();
  const testWechatMut = useTestWechat();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!selectedId && schemes.length > 0) setSelectedId(schemes[0].id);
  }, [schemes, selectedId]);

  useEffect(() => {
    if (window.pywebview?.api?.getAppInfo) {
      window.pywebview.api.getAppInfo().then(setAppInfo).catch(() => setAppInfo(null));
    }
  }, []);

  const wechatAccounts = wechatData.accounts;
  const wechatConversations = wechatData.conversations;
  const wechatStatus = wechatData.status;
  const wechatAccount = wechatData.account;

  const wechatDotColor = useMemo(() => {
    if (!wechatStatus?.running) return "bg-muted-foreground/50";
    if (!wechatAccount) return "bg-muted-foreground/50";
    switch (wechatAccount.status) {
      case "online": return "bg-green-500";
      case "connecting": return "bg-yellow-500";
      case "reconnecting": return "bg-yellow-500";
      case "session_expired": return "bg-red-500";
      case "error": return "bg-red-500";
      case "stopped": return "bg-muted-foreground/50";
      default: return "bg-muted-foreground/50";
    }
  }, [wechatStatus?.running, wechatAccount]);

  const wechatTooltipText = useMemo(() => {
    if (!wechatStatus?.running) return "微信桥接服务未运行";
    if (!wechatAccount) return "微信未绑定，点击扫码绑定";
    const label = STATUS_LABELS[wechatAccount.status] || wechatAccount.status || "未知";
    let text = `微信${label}`;
    if (wechatAccount.account_id) text += ` · ${wechatAccount.account_id}`;
    if (wechatAccount.last_error) text += ` · ${wechatAccount.last_error}`;
    return text;
  }, [wechatStatus?.running, wechatAccount]);

  const selectedRuntime = useMemo(
    () => status.schemes?.find((s) => s.id === selectedId),
    [status.schemes, selectedId]
  );

  const metrics = [
    { label: "方案总数", value: system?.total_schemes ?? schemes.length, icon: ListChecks, color: "bg-blue-500/10 text-blue-500" },
    { label: "启用方案", value: system?.active_schemes ?? 0, icon: CheckCircle2, color: "bg-green-500/10 text-green-500" },
    { label: "运行任务", value: status.running_tasks ?? 0, icon: Activity, color: "bg-amber-500/10 text-amber-500" },
    { label: "关键词数", value: system?.total_keywords ?? 0, icon: Tag, color: "bg-purple-500/10 text-purple-500" },
  ];

  async function handleCreateScheme(payload) {
    try {
      const res = await createSchemeMut.mutateAsync(payload);
      setModal(null);
      toast.success("方案已创建");
      if (res.data?.id) setSelectedId(res.data.id);
    } catch (e) { toast.error(`创建失败：${e.message}`); }
  }

  async function handleUpdateScheme(payload) {
    try {
      await updateSchemeMut.mutateAsync({ id: payload.id, ...payload });
      setModal(null);
      toast.success("方案已更新");
    } catch (e) { toast.error(`更新失败：${e.message}`); }
  }

  async function handleToggleScheme(scheme) {
    try {
      await updateSchemeMut.mutateAsync({ id: scheme.id, is_active: !scheme.is_active });
      toast.success(scheme.is_active ? "方案已停用" : "方案已启用");
    } catch (e) { toast.error(`操作失败：${e.message}`); }
  }

  async function handleDeleteScheme(id) {
    if (!window.confirm("确定删除这个方案和相关历史记录吗？")) return;
    try {
      await deleteSchemeMut.mutateAsync(id);
      setSelectedId(null);
      toast.success("方案已删除");
    } catch (e) { toast.error(`删除失败：${e.message}`); }
  }

  async function handleAddKeyword(payload) {
    try {
      await addKeywordMut.mutateAsync(payload);
      setModal(null);
      toast.success("关键词已添加");
    } catch (e) { toast.error(`添加失败：${e.message}`); }
  }

  async function handleUpdateKeyword(payload) {
    try {
      await updateKeywordMut.mutateAsync(payload);
      setModal(null);
      toast.success("关键词已更新");
    } catch (e) { toast.error(`更新失败：${e.message}`); }
  }

  async function handleDeleteKeyword(id) {
    if (!window.confirm("确定删除这个关键词吗？")) return;
    try {
      await deleteKeywordMut.mutateAsync(id);
      toast.success("关键词已删除");
    } catch (e) { toast.error(`删除失败：${e.message}`); }
  }

  async function handleRestartScheme(id) {
    try {
      const res = await restartSchemeMut.mutateAsync(id);
      toast.success(res.message || "方案监控已重启");
    } catch (e) { toast.error(`重启失败：${e.message}`); }
  }

  async function handleTestWebhook(scheme) {
    try {
      const webhookUrl = scheme.dingtalk_webhook || globalWebhook;
      const secret = scheme.dingtalk_secret || globalSecret;
      const res = await testWebhookMut.mutateAsync({ webhook_url: webhookUrl, secret });
      if (res.success) toast.success(res.message); else toast.warning(res.message);
    } catch (e) { toast.error(`测试失败：${e.message}`); }
  }

  async function handleTestWechat(scheme) {
    try {
      const res = await testWechatMut.mutateAsync({ account_id: scheme.wechat_account_id || "", conversation_id: scheme.wechat_targets || "" });
      if (res.success) toast.success(res.message); else toast.warning(res.message);
    } catch (e) { toast.error(`测试失败：${e.message}`); }
  }

  function handleRefreshAll() { qc.invalidateQueries(); }

  function minimizeToTray() {
    if (window.pywebview?.api?.minimizeToTray) window.pywebview.api.minimizeToTray();
  }

  return (
    <SidebarProvider>
      <AppSidebar
        schemes={schemes}
        status={status}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onToggle={handleToggleScheme}
        onNewScheme={() => setModal({ type: "scheme", mode: "create" })}
      />

      <SidebarInset>
        {/* Top bar */}
        <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-4 backdrop-blur-sm">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4" />
          <div className="flex flex-1 items-center gap-2">
            <h1 className="text-lg font-semibold">什么值得买好价监控</h1>
            {status.running && (
              <Badge variant="success" className="gap-1">
                <span className="flex size-1.5 rounded-full bg-green-500 animate-pulse" />
                运行中
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" onClick={() => setModal({ type: "dingtalk" })} className="relative">
                  <Bell size={18} />
                  <span className={`absolute right-1 top-1 size-2 rounded-full border border-background ${globalWebhook ? "bg-green-500" : "bg-muted-foreground/50"}`} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {globalWebhook ? "钉钉通知已配置" : "钉钉未配置，点击设置"}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" onClick={() => setModal({ type: "wechat" })} className="relative">
                  <MessageCircle size={18} />
                  <span className={`absolute right-1 top-1 size-2 rounded-full border border-background ${wechatDotColor}`} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {wechatTooltipText}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" onClick={handleRefreshAll}>
                  <RefreshCw size={18} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>刷新全部</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" onClick={() => setModal({ type: "settings" })}>
                  <Settings size={18} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>全局设置</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
                  {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>切换主题</TooltipContent>
            </Tooltip>
            {window.pywebview?.api && (
              <Button variant="outline" size="sm" onClick={minimizeToTray} className="ml-2">
                隐藏到托盘
              </Button>
            )}
          </div>
        </header>

        {/* Main content */}
        <div className="flex flex-1 flex-col gap-4 p-4">
          {/* Metrics row */}
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {metrics.map(({ label, value, icon: Icon, color }) => (
              <MetricCard key={label} label={label} value={value} icon={Icon} color={color} />
            ))}
          </section>

          {/* Detail or Welcome */}
          {selectedId ? (
            detailLoading && !detail ? (
              <DetailSkeleton />
            ) : detail ? (
              <DetailView
                detail={detail}
                selectedRuntime={selectedRuntime}
                wechatAccounts={wechatAccounts}
                globalWebhook={globalWebhook}
                onEdit={(d) => setModal({ type: "scheme", mode: "edit", data: d })}
                onToggle={handleToggleScheme}
                onRestart={handleRestartScheme}
                onDelete={handleDeleteScheme}
                onAddKeyword={() => setModal({ type: "keyword", mode: "create" })}
                onEditKeyword={(kw) => setModal({ type: "keyword", mode: "edit", data: kw })}
                onDeleteKeyword={handleDeleteKeyword}
                onTestWebhook={handleTestWebhook}
                onTestWechat={handleTestWechat}
                onOpenWechat={() => setModal({ type: "wechat" })}
              />
            ) : (
              <DetailSkeleton />
            )
          ) : (
            <WelcomeView onNewScheme={() => setModal({ type: "scheme", mode: "create" })} />
          )}

          {/* Status bar */}
          <footer className="mt-auto flex items-center justify-between pt-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className={`flex size-1.5 rounded-full ${status.running ? "bg-green-500 animate-pulse" : "bg-muted-foreground/40"}`} />
              {status.running_tasks ? `${status.running_tasks} 个方案正在监控` : "暂无方案运行"}
            </span>
            <span>{appInfo?.dataDir || system?.data_dir || "runtime data"}</span>
          </footer>
        </div>
      </SidebarInset>

      {/* Modals */}
      {modal?.type === "scheme" && (
        <SchemeModal
          mode={modal.mode}
          initial={modal.data}
          onClose={() => setModal(null)}
          onSubmit={modal.mode === "edit" ? handleUpdateScheme : handleCreateScheme}
          wechatConversations={wechatConversations}
          wechatAccount={wechatAccount}
        />
      )}
      {modal?.type === "keyword" && (
        <KeywordModal
          mode={modal.mode}
          initial={modal.data}
          onClose={() => setModal(null)}
          onSubmit={modal.mode === "edit" ? handleUpdateKeyword : handleAddKeyword}
        />
      )}
      {modal?.type === "settings" && <SettingsModal onClose={() => setModal(null)} />}
      {modal?.type === "dingtalk" && <DingtalkModal onClose={() => setModal(null)} />}
      {modal?.type === "wechat" && (
        <WechatModal
          status={wechatStatus}
          account={wechatAccount}
          conversations={wechatConversations}
          onClose={() => setModal(null)}
        />
      )}
    </SidebarProvider>
  );
}
