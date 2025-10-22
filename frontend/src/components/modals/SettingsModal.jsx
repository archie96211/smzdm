import React, { useState, useEffect } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useGlobalSettings, useUpdateSettings, useRestartServer } from "@/helpers/api";
import { toast } from "sonner";

export default function SettingsModal({ onClose }) {
  const { data: settings } = useGlobalSettings();
  const updateSettingsMut = useUpdateSettings();
  const restartServerMut = useRestartServer();
  const [form, setForm] = useState({
    image_server_host: "127.0.0.1",
    image_server_port: 18080,
    server_port: 18080,
  });
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    if (settings) {
      setForm({
        image_server_host: settings.image_server_host?.value || "127.0.0.1",
        image_server_port: Number(settings.image_server_port?.value || 18080),
        server_port: Number(settings.server_port?.value || 18080),
      });
    }
  }, [settings]);

  async function handleSubmit(event) {
    event.preventDefault();
    const portChanged = form.server_port !== Number(settings?.server_port?.value || 18080);
    try {
      await updateSettingsMut.mutateAsync({
        ...form,
        dingtalk_webhook: settings?.dingtalk_webhook?.value || "",
        dingtalk_secret: settings?.dingtalk_secret?.value || "",
      });

      if (portChanged) {
        setRestarting(true);
        toast.info("服务端口已修改，正在重启服务...");
        try {
          await restartServerMut.mutateAsync(form.server_port);
        } catch {
          // Expected: connection will drop during restart
        }
        const newPort = form.server_port;
        const protocol = window.location.protocol;
        const hostname = window.location.hostname;
        const pollUrl = `${protocol}//${hostname}:${newPort}/api/health`;
        let recovered = false;
        for (let i = 0; i < 30; i++) {
          await new Promise((r) => setTimeout(r, 1000));
          try {
            const res = await fetch(pollUrl);
            if (res.ok) { recovered = true; break; }
          } catch { /* still down */ }
        }
        setRestarting(false);
        if (recovered) {
          toast.success("服务已重启，即将跳转...");
          setTimeout(() => {
            window.location.href = `${protocol}//${hostname}:${newPort}/static/`;
          }, 800);
        } else {
          toast.error("服务重启超时，请手动检查");
        }
      } else {
        onClose();
        toast.success("全局设置已保存");
      }
    } catch (e) {
      toast.error(`保存失败：${e.message}`);
      setRestarting(false);
    }
  }

  return (
    <Dialog open onOpenChange={(v) => { if (!v && !restarting) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>全局设置</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label>图片服务地址</Label>
            <Input value={form.image_server_host}
              onChange={(e) => setForm({ ...form, image_server_host: e.target.value })}
              disabled={restarting} />
          </div>
          <div className="grid gap-2">
            <Label>图片服务端口</Label>
            <Input type="number" min="1" max="65535" value={form.image_server_port}
              onChange={(e) => setForm({ ...form, image_server_port: Number(e.target.value) })}
              disabled={restarting} />
          </div>
          <div className="col-span-2 grid gap-2">
            <Label>服务端口</Label>
            <Input type="number" min="1" max="65535" value={form.server_port}
              onChange={(e) => setForm({ ...form, server_port: Number(e.target.value) })}
              disabled={restarting} />
            <p className="text-xs text-muted-foreground">
              修改服务端口后保存将自动重启后端服务，浏览器会跳转到新端口。
            </p>
          </div>
          <p className="col-span-2 rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
            钉钉卡片里的商品图会先缓存到本机，再使用这里配置的公网 IP 生成图片链接。
            腾讯云服务器会自动尝试识别公网 IP，请确保该端口能被钉钉访问。
          </p>
          <DialogFooter className="col-span-2 mt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={restarting}>取消</Button>
            <Button type="submit" disabled={restarting || updateSettingsMut.isPending}>
              {restarting ? "重启中..." : "保存"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
