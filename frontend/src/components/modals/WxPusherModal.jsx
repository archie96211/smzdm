import React, { useState, useEffect } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useGlobalSettings, useUpdateSettings, useTestWxPusher } from "@/helpers/api";
import { toast } from "sonner";

export default function WxPusherModal({ onClose }) {
  const { data: settings } = useGlobalSettings();
  const updateSettingsMut = useUpdateSettings();
  const testWxPusherMut = useTestWxPusher();
  const [form, setForm] = useState({
    wxpusher_app_token: "",
    wxpusher_uid: "",
  });

  useEffect(() => {
    if (settings) {
      setForm({
        wxpusher_app_token: settings.wxpusher_app_token?.value || "",
        wxpusher_uid: settings.wxpusher_uid?.value || "",
      });
    }
  }, [settings]);

  async function handleSubmit(event) {
    event.preventDefault();
    try {
      await updateSettingsMut.mutateAsync({
        image_server_host: settings?.image_server_host?.value || "127.0.0.1",
        image_server_port: Number(settings?.image_server_port?.value || 18080),
        server_port: Number(settings?.server_port?.value || 18080),
        dingtalk_webhook: settings?.dingtalk_webhook?.value || "",
        dingtalk_secret: settings?.dingtalk_secret?.value || "",
        wxpusher_app_token: form.wxpusher_app_token,
        wxpusher_uid: form.wxpusher_uid,
      });
      toast.success("WxPusher 配置已保存");
      onClose();
    } catch (e) {
      toast.error(`保存失败：${e.message}`);
    }
  }

  async function handleTest() {
    if (!form.wxpusher_app_token.trim() || !form.wxpusher_uid.trim()) {
      toast.warning("请先填写 AppToken 和 UID");
      return;
    }
    try {
      const res = await testWxPusherMut.mutateAsync({
        app_token: form.wxpusher_app_token.trim(),
        uid: form.wxpusher_uid.trim(),
      });
      if (res.success) toast.success(res.message);
      else toast.warning(res.message);
    } catch (e) {
      toast.error(`测试失败：${e.message}`);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>WxPusher 通知设置</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            配置全局 WxPusher AppToken 和 UID，各监控方案默认使用此配置发送通知，也可在方案中自定义覆盖。
            在 <a href="https://wxpusher.zjiecode.com/" target="_blank" rel="noopener noreferrer" className="text-primary underline">WxPusher 管理后台</a> 创建应用获取 AppToken，扫码关注后获取 UID。
          </p>
          <div className="grid gap-2">
            <Label>AppToken</Label>
            <Input value={form.wxpusher_app_token}
              onChange={(e) => setForm({ ...form, wxpusher_app_token: e.target.value })}
              placeholder="AT_xxxxxxxxxxxxxxxx" />
          </div>
          <div className="grid gap-2">
            <Label>UID</Label>
            <Input value={form.wxpusher_uid}
              onChange={(e) => setForm({ ...form, wxpusher_uid: e.target.value })}
              placeholder="UID_xxxxxxxxxxxxxxxx" />
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={handleTest} disabled={testWxPusherMut.isPending}>
              {testWxPusherMut.isPending ? "测试中..." : "发送测试"}
            </Button>
            <div className="flex-1" />
            <Button type="button" variant="outline" onClick={onClose}>取消</Button>
            <Button type="submit" disabled={updateSettingsMut.isPending}>保存</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
