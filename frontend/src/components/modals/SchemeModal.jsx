import React, { useState, useEffect } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { useGlobalSettings } from "@/helpers/api";

const DEFAULT_SCHEME = {
  name: "", keyword: "", refresh_interval: 60,
  dingtalk_webhook: "", dingtalk_secret: "",
  wechat_enabled: false, wechat_account_id: "", wechat_targets: "",
  wxpusher_enabled: false, wxpusher_app_token: "", wxpusher_uid: "",
  is_active: true,
};

function formatConversation(conversation) {
  const name = conversation.remark || conversation.user_id || conversation.id;
  const text = conversation.last_text ? ` / ${conversation.last_text}` : "";
  return `${name}${text}`;
}

export default function SchemeModal({ mode, initial, onSubmit, onClose, wechatConversations = [], wechatAccount = null }) {
  const { data: globalSettings } = useGlobalSettings();
  const globalWebhook = globalSettings?.dingtalk_webhook?.value || "";
  const globalWxPusherToken = globalSettings?.wxpusher_app_token?.value || "";
  const globalWxPusherUid = globalSettings?.wxpusher_uid?.value || "";
  const isCreate = mode === "create";
  const wechatReady = Boolean(wechatAccount && wechatConversations.length > 0);
  const [form, setForm] = useState({
    ...DEFAULT_SCHEME,
    ...(initial || {}),
    wechat_enabled: isCreate ? wechatReady : Boolean(initial?.wechat_enabled),
  });
  const [dingtalkEnabled, setDingtalkEnabled] = useState(
    isCreate ? Boolean(globalWebhook) : Boolean(initial?.dingtalk_webhook || initial?.dingtalk_secret)
  );
  const [useCustomWebhook, setUseCustomWebhook] = useState(Boolean(initial?.dingtalk_webhook));
  const [wxpusherEnabled, setWxpusherEnabled] = useState(
    isCreate ? Boolean(globalWxPusherToken && globalWxPusherUid) : Boolean(initial?.wxpusher_enabled)
  );
  const [useCustomWxPusher, setUseCustomWxPusher] = useState(Boolean(initial?.wxpusher_app_token));
  const title = mode === "edit" ? "编辑监控方案" : "新建监控方案";

  useEffect(() => {
    if (form.wechat_enabled && wechatConversations.length === 1 && !form.wechat_targets) {
      setForm((f) => ({ ...f, wechat_targets: wechatConversations[0].id }));
    }
  }, [form.wechat_enabled, form.wechat_targets, wechatConversations]);

  function submitForm(event) {
    event.preventDefault();
    const payload = {
      ...form,
      name: String(form.name || "").trim(),
      dingtalk_webhook: dingtalkEnabled && useCustomWebhook ? String(form.dingtalk_webhook || "").trim() : "",
      dingtalk_secret: dingtalkEnabled && useCustomWebhook ? String(form.dingtalk_secret || "").trim() : "",
      wechat_enabled: Boolean(form.wechat_enabled),
      wechat_account_id: String(form.wechat_account_id || "").trim(),
      wechat_targets: Boolean(form.wechat_enabled) ? String(form.wechat_targets || "").trim() : "",
      wxpusher_enabled: Boolean(wxpusherEnabled),
      wxpusher_app_token: wxpusherEnabled && useCustomWxPusher ? String(form.wxpusher_app_token || "").trim() : "",
      wxpusher_uid: wxpusherEnabled && useCustomWxPusher ? String(form.wxpusher_uid || "").trim() : "",
    };
    if (mode === "create") {
      payload.keyword = String(form.keyword || "").trim();
    } else {
      delete payload.keyword;
    }
    onSubmit(payload);
  }

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submitForm} className="grid grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label>方案名称</Label>
            <Input required pattern=".*\S.*" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label>刷新间隔（秒）</Label>
            <Input type="number" min="30" max="3600" value={form.refresh_interval}
              onChange={(e) => setForm({ ...form, refresh_interval: Number(e.target.value) })} />
          </div>
          {mode === "create" && (
            <div className="col-span-2 grid gap-2">
              <Label>关键词</Label>
              <Input required pattern=".*\S.*" value={form.keyword || ""}
                onChange={(e) => setForm({ ...form, keyword: e.target.value })} />
            </div>
          )}
          <div className="col-span-2 flex items-center gap-3">
            <Switch checked={dingtalkEnabled} onCheckedChange={setDingtalkEnabled} id="dingtalk" />
            <Label htmlFor="dingtalk">启用钉钉通知</Label>
          </div>
          {dingtalkEnabled && (
            <div className="col-span-2 flex flex-col gap-2 rounded-lg border border-border bg-muted/20 p-3">
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={!useCustomWebhook} onChange={() => setUseCustomWebhook(false)} />
                <span>使用全局 Webhook{globalWebhook ? "" : "（未配置）"}</span>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={useCustomWebhook} onChange={() => setUseCustomWebhook(true)} />
                <span>自定义 Webhook</span>
              </label>
              {useCustomWebhook && (
                <div className="mt-1 flex flex-col gap-2">
                  <Input value={form.dingtalk_webhook || ""}
                    onChange={(e) => setForm({ ...form, dingtalk_webhook: e.target.value })}
                    placeholder="Webhook URL" />
                  <Input value={form.dingtalk_secret || ""}
                    onChange={(e) => setForm({ ...form, dingtalk_secret: e.target.value })}
                    placeholder="加签密钥（可选）" />
                </div>
              )}
            </div>
          )}
          <div className="col-span-2 flex items-center gap-3">
            <Switch checked={Boolean(form.wechat_enabled)}
              onCheckedChange={(v) => setForm({ ...form, wechat_enabled: v })} id="wechat" />
            <Label htmlFor="wechat">启用微信通知</Label>
          </div>
          {form.wechat_enabled && (
            <div className="col-span-2 grid gap-2">
              <Label>微信接收会话</Label>
              {wechatConversations.length === 0 ? (
                <p className="rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
                  还没有接收会话，请先用接收通知的微信或群给 bot 发一条消息。
                </p>
              ) : wechatConversations.length === 1 ? (
                <div className="flex items-center gap-2 rounded-md border border-border bg-muted/20 p-3 text-sm">
                  <span className="text-muted-foreground">将使用会话：</span>
                  <strong className="truncate">{formatConversation(wechatConversations[0])}</strong>
                </div>
              ) : (
                <Select value={form.wechat_targets || ""} onValueChange={(v) => {
                  setForm({ ...form, wechat_targets: v });
                }}>
                  <SelectTrigger><SelectValue placeholder="选择接收通知的会话" /></SelectTrigger>
                  <SelectContent>
                    {wechatConversations.map((c) => (
                      <SelectItem key={c.id} value={c.id}>{formatConversation(c)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}
          <div className="col-span-2 flex items-center gap-3">
            <Switch checked={wxpusherEnabled} onCheckedChange={setWxpusherEnabled} id="wxpusher" />
            <Label htmlFor="wxpusher">启用 WxPusher 通知</Label>
          </div>
          {wxpusherEnabled && (
            <div className="col-span-2 flex flex-col gap-2 rounded-lg border border-border bg-muted/20 p-3">
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={!useCustomWxPusher} onChange={() => setUseCustomWxPusher(false)} />
                <span>使用全局配置{globalWxPusherToken && globalWxPusherUid ? "" : "（未配置）"}</span>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" checked={useCustomWxPusher} onChange={() => setUseCustomWxPusher(true)} />
                <span>自定义配置</span>
              </label>
              {useCustomWxPusher && (
                <div className="mt-1 flex flex-col gap-2">
                  <Input value={form.wxpusher_app_token || ""}
                    onChange={(e) => setForm({ ...form, wxpusher_app_token: e.target.value })}
                    placeholder="AppToken (AT_xxx)" />
                  <Input value={form.wxpusher_uid || ""}
                    onChange={(e) => setForm({ ...form, wxpusher_uid: e.target.value })}
                    placeholder="UID (UID_xxx)" />
                </div>
              )}
            </div>
          )}
          <DialogFooter className="col-span-2 mt-2">
            <Button type="button" variant="outline" onClick={onClose}>取消</Button>
            <Button type="submit">保存</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
