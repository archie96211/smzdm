import React, { useState, useEffect } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { apiRequest, useSetConversationRemark, useTestWechat } from "@/helpers/api";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Pencil, Check, X } from "lucide-react";

const STATUS_LABELS = {
  online: ["在线", "success"],
  connecting: ["连接中", "secondary"],
  reconnecting: ["重连中", "warning"],
  session_expired: ["会话过期", "destructive"],
  error: ["异常", "destructive"],
  stopped: ["已停止", "secondary"],
};

const STATUS_DOT_COLORS = {
  online: "bg-green-500",
  connecting: "bg-yellow-500",
  reconnecting: "bg-yellow-500",
  session_expired: "bg-red-500",
  error: "bg-red-500",
  stopped: "bg-muted-foreground/50",
};

function EmptyText({ text }) {
  return (
    <div className="flex flex-col items-center gap-2 p-6 text-center text-muted-foreground">
      <span>{text}</span>
    </div>
  );
}

function ConversationRow({ conversation }) {
  const [editing, setEditing] = useState(false);
  const [remarkValue, setRemarkValue] = useState(conversation.remark || "");
  const remarkMut = useSetConversationRemark();

  async function saveRemark() {
    await remarkMut.mutateAsync({ conversationId: conversation.id, remark: remarkValue.trim() });
    setEditing(false);
  }

  const displayName = conversation.remark || conversation.user_id;
  const subInfo = conversation.remark ? conversation.user_id : "";

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/20 p-3">
      <div className="flex items-center gap-2 min-w-0">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <strong className="truncate">{displayName}</strong>
            {subInfo && <span className="text-sm text-muted-foreground truncate">{subInfo}</span>}
          </div>
          {conversation.last_text && (
            <span className="block truncate text-sm text-muted-foreground">{conversation.last_text}</span>
          )}
        </div>
        {!editing && (
          <Button variant="ghost" size="icon" className="size-7 shrink-0" onClick={() => setEditing(true)}>
            <Pencil size={14} />
          </Button>
        )}
      </div>
      {editing && (
        <div className="flex items-center gap-1">
          <Input
            value={remarkValue}
            onChange={(e) => setRemarkValue(e.target.value)}
            placeholder="输入备注名"
            className="h-8 flex-1"
            onKeyDown={(e) => { if (e.key === "Enter") saveRemark(); if (e.key === "Escape") setEditing(false); }}
          />
          <Button variant="ghost" size="icon" className="size-7 shrink-0" onClick={saveRemark} disabled={remarkMut.isPending}>
            <Check size={14} />
          </Button>
          <Button variant="ghost" size="icon" className="size-7 shrink-0" onClick={() => { setEditing(false); setRemarkValue(conversation.remark || ""); }}>
            <X size={14} />
          </Button>
        </div>
      )}
    </div>
  );
}

export default function WechatModal({ status, account, conversations = [], onClose }) {
  const [login, setLogin] = useState(null);
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();
  const testWechatMut = useTestWechat();

  useEffect(() => {
    if (!login?.id || ["confirmed", "failed", "expired", "cancelled"].includes(login.status)) return undefined;
    let pendingTimeout = null;
    const timer = window.setInterval(async () => {
      try {
        const response = await apiRequest(`/api/wechat/login/status/${login.id}`);
        setLogin(response.data);
        if (response.data.status === "confirmed") {
          await apiRequest("/api/wechat/reload", { method: "POST" });
          qc.invalidateQueries({ queryKey: ["wechat-status"] });
          pendingTimeout = setTimeout(() => qc.invalidateQueries({ queryKey: ["wechat-status"] }), 3000);
        }
      } catch (error) {
        setLogin((current) => ({ ...(current || {}), status: "failed", error: error.message }));
      }
    }, 2000);
    return () => { window.clearInterval(timer); if (pendingTimeout) clearTimeout(pendingTimeout); };
  }, [login?.id, login?.status, qc]);

  async function startLogin() {
    setBusy(true);
    try {
      const response = await apiRequest("/api/wechat/login/start", { method: "POST" });
      setLogin(response.data);
    } finally {
      setBusy(false);
    }
  }

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: ["wechat-status"] });
  }

  async function handleTestWechat() {
    const target = conversations[0];
    if (!target) {
      toast.warning("没有可用的会话，先用微信给 bot 发一条消息");
      return;
    }
    try {
      const res = await testWechatMut.mutateAsync({
        conversation_id: target.id,
        text: "SMZDM 监控系统测试消息\n\n如果你收到了这条消息，说明微信通知配置成功！",
      });
      if (res.success) toast.success(res.message);
      else toast.warning(res.message);
    } catch (e) {
      toast.error(`测试失败：${e.message}`);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>微信绑定</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          {/* Bridge status */}
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${status?.running ? "bg-green-500" : "bg-muted-foreground/50"}`} />
            <span>{status?.running ? "桥接服务运行中" : "微信桥接服务未运行"}</span>
          </div>

          {/* Single account card */}
          {account ? (() => {
            const [label, variant] = STATUS_LABELS[account.status] || [account.status || "未知", "secondary"];
            const dotColor = STATUS_DOT_COLORS[account.status] || "bg-muted-foreground/50";
            return (
              <div className="rounded-lg border border-border bg-muted/20 p-4">
                <div className="flex items-center gap-2">
                  <span className={`size-2.5 rounded-full ${dotColor}`} />
                  <strong className="text-sm">{account.account_id}</strong>
                  <Badge variant={variant}>{label}</Badge>
                </div>
                <div className="mt-2 flex flex-col gap-1 text-sm text-muted-foreground">
                  {account.bot_id && <span>Bot ID: {account.bot_id}</span>}
                  {account.last_activity && (
                    <span>最后活动: {new Date(account.last_activity).toLocaleString("zh-CN")}</span>
                  )}
                  {account.last_error && (
                    <span className="text-destructive">错误: {account.last_error}</span>
                  )}
                </div>
              </div>
            );
          })() : (
            <EmptyText text="还没有绑定微信账号，点击下方按钮扫码绑定" />
          )}

          {/* Conversations with remark editing */}
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">接收会话</span>
            <div className="max-h-[220px] overflow-auto">
              {conversations.map((conversation) => (
                <ConversationRow key={conversation.id} conversation={conversation} />
              ))}
              {!conversations.length && (
                <EmptyText text="还没有接收会话，先用接收通知的微信或群给 bot 发一条消息" />
              )}
            </div>
          </div>

          {login?.qr_image_data_url && !["confirmed", "failed", "expired", "cancelled"].includes(login.status) && (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-muted/20 p-4">
              <img src={login.qr_image_data_url} alt="微信扫码绑定二维码" className="h-[280px] w-[280px] rounded-lg bg-white" />
              <span>{login.status === "scanned" ? "已扫码，请在手机微信确认" : "请使用微信扫码绑定"}</span>
            </div>
          )}
          {login?.status === "confirmed" && <p className="text-sm text-muted-foreground">绑定成功：{login.account_id}</p>}
          {login?.error && <p className="text-sm text-destructive">绑定失败：{login.error}</p>}

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleRefresh}>刷新状态</Button>
            {account && conversations.length > 0 && (
              <Button variant="outline" onClick={handleTestWechat} disabled={testWechatMut.isPending}>
                {testWechatMut.isPending ? "测试中..." : "发送测试"}
              </Button>
            )}
            <Button variant={account ? "destructive" : "default"} disabled={busy} onClick={startLogin}>
              {busy ? "正在获取二维码" : account ? "更换微信绑定" : "扫码绑定微信"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
