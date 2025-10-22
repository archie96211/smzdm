import React, { useState, useEffect } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useGlobalSettings, useUpdateSettings, useTestWebhook } from "@/helpers/api";
import { toast } from "sonner";

export default function DingtalkModal({ onClose }) {
  const { data: settings } = useGlobalSettings();
  const updateSettingsMut = useUpdateSettings();
  const testWebhookMut = useTestWebhook();
  const [form, setForm] = useState({
    dingtalk_webhook: "",
    dingtalk_secret: "",
  });

  useEffect(() => {
    if (settings) {
      setForm({
        dingtalk_webhook: settings.dingtalk_webhook?.value || "",
        dingtalk_secret: settings.dingtalk_secret?.value || "",
      });
    }
  }, [settings]);

  async function handleSubmit(event) {
    event.preventDefault();
    try {
      await updateSettingsMut.mutateAsync({
        image_server_host: settings?.image_server_host?.value || "127.0.0.1",
        image_server_port: Number(settings?.image_server_port?.value || 8000),
        dingtalk_webhook: form.dingtalk_webhook,
        dingtalk_secret: form.dingtalk_secret,
      });
      toast.success("钉钉 Webhook 已保存");
      onClose();
    } catch (e) {
      toast.error(`保存失败：${e.message}`);
    }
  }

  async function handleTest() {
    if (!form.dingtalk_webhook.trim()) {
      toast.warning("请先填写 Webhook URL");
      return;
    }
    try {
      const res = await testWebhookMut.mutateAsync({
        webhook_url: form.dingtalk_webhook.trim(),
        secret: form.dingtalk_secret.trim(),
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
          <DialogTitle>钉钉通知设置</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            配置全局钉钉 Webhook，各监控方案默认使用此配置发送通知，也可在方案中自定义覆盖。
          </p>
          <div className="grid gap-2">
            <Label>Webhook URL</Label>
            <Input value={form.dingtalk_webhook}
              onChange={(e) => setForm({ ...form, dingtalk_webhook: e.target.value })}
              placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
          </div>
          <div className="grid gap-2">
            <Label>加签密钥（可选）</Label>
            <Input value={form.dingtalk_secret}
              onChange={(e) => setForm({ ...form, dingtalk_secret: e.target.value })}
              placeholder="SEC..." />
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={handleTest} disabled={testWebhookMut.isPending}>
              {testWebhookMut.isPending ? "测试中..." : "发送测试"}
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
