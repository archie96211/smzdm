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
import { useBarkSettings, useSaveBarkSettings, useTestBark } from "@/helpers/api";
import { toast } from "sonner";

function Choice({ id, label, value, options, onChange }) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id}><SelectValue /></SelectTrigger>
        <SelectContent>{options.map(([key, text]) => <SelectItem key={key} value={key}>{text}</SelectItem>)}</SelectContent>
      </Select>
    </div>
  );
}

export default function BarkModal({ schemeId, onClose }) {
  const { data, isLoading, error } = useBarkSettings(schemeId);
  const saveMut = useSaveBarkSettings(schemeId);
  const testMut = useTestBark(schemeId);
  const [form, setForm] = useState(null);
  const [useGlobal, setUseGlobal] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [clearSecrets, setClearSecrets] = useState([]);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data && !dirty) {
      setForm(data.config);
      setUseGlobal(data.use_global);
      setEnabled(data.enabled);
    }
  }, [data, dirty]);

  function update(key, value) {
    setDirty(true);
    setForm((current) => ({ ...current, [key]: value }));
  }

  function payload() {
    return { config: form, use_global: useGlobal, enabled: schemeId ? enabled : null, clear_secrets: clearSecrets };
  }

  async function submit(event) {
    event.preventDefault();
    try {
      await saveMut.mutateAsync(payload());
      toast.success("Bark 配置已保存");
      onClose();
    } catch (e) {
      toast.error(`保存失败：${e.message}`);
    }
  }

  async function test() {
    try {
      const result = await testMut.mutateAsync(payload());
      if (result.success) toast.success(result.message);
      else toast.warning(result.message);
    } catch (e) {
      toast.error(`测试失败：${e.message}`);
    }
  }

  function textField(key, label, placeholder = "", type = "text", extra = {}) {
    return (
      <div className="grid gap-2">
        <Label htmlFor={`bark-${key}`}>{label}</Label>
        <Input id={`bark-${key}`} type={type} value={form[key] ?? ""} placeholder={placeholder}
          autoComplete={type === "password" ? "new-password" : undefined}
          onChange={(event) => update(key, type === "number" ? (event.target.value === "" ? null : Number(event.target.value)) : event.target.value)} {...extra} />
      </div>
    );
  }

  function toggle(key, label) {
    return (
      <div className="flex items-center gap-3">
        <Switch id={`bark-${key}`} checked={Boolean(form[key])} onCheckedChange={(value) => update(key, value)} />
        <Label htmlFor={`bark-${key}`}>{label}</Label>
      </div>
    );
  }

  function clearKey(key, label) {
    return form[`has_${key}`] && (
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <input type="checkbox" checked={clearSecrets.includes(key)} onChange={(event) => {
          setDirty(true);
          setClearSecrets((current) => event.target.checked ? [...current, key] : current.filter((item) => item !== key));
        }} />{label}
      </label>
    );
  }

  return (
    <Dialog open onOpenChange={(value) => { if (!value) onClose(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>{schemeId ? "方案 Bark 通知" : "全局 Bark 通知"}</DialogTitle></DialogHeader>
        {error && <p className="text-sm text-destructive">加载失败：{error.message}</p>}
        {isLoading || !form ? <p className="text-sm text-muted-foreground">正在读取配置…</p> : (
          <form onSubmit={submit} className="flex flex-col gap-4">
            {schemeId ? (
              <div className="flex flex-wrap gap-5">
                <div className="flex items-center gap-2">
                  <Switch id="bark-enabled" checked={enabled} onCheckedChange={(value) => { setDirty(true); setEnabled(value); }} />
                  <Label htmlFor="bark-enabled">启用此方案通知</Label>
                </div>
                <div className="flex items-center gap-2">
                  <Switch id="bark-inherit" checked={useGlobal} onCheckedChange={(value) => { setDirty(true); setUseGlobal(value); }} />
                  <Label htmlFor="bark-inherit">使用全局配置</Label>
                </div>
              </div>
            ) : <p className="text-sm text-muted-foreground">先配置接收设备，再在需要的监控方案中开启 Bark。修改全局配置会影响所有使用它的方案。</p>}
            {schemeId && useGlobal ? <p className="text-sm text-muted-foreground">发送与测试均使用已保存的全局配置。关闭此开关可为当前方案配置独立的设备和通知选项。</p> : (
              <>
                {textField("push_url", "Bark 推送地址", form.has_device_key ? "已保存，留空保持不变" : "https://api.day.app/你的设备Key/", "password")}
                <p className="text-xs text-muted-foreground">直接粘贴 Bark App 复制的完整推送地址，包含设备 Key，支持自建服务。地址仅用于发送，不会回显；修改分组等选项时可留空。</p>
                {form.has_device_key && <p className="text-xs text-muted-foreground">已配置服务：{form.server_url} · 设备 Key 已隐藏</p>}
                {clearKey("device_key", "清除已保存的推送凭据")}
                {textField("group", "通知分组", "SMZDM · {scheme}")}
                <p className="text-xs text-muted-foreground">分组与复制内容支持 {"{scheme}、{mall}、{keyword}、{url}"} 占位符。留空分组则不指定分组。</p>
                {textField("icon", "通知图标 URL", "https://example.com/icon.png")}
                <p className="text-xs text-muted-foreground">iOS 15+ 支持；同一 URL 会被 Bark 缓存，更新图标时请更换 URL。</p>
                {toggle("image_enabled", "附带商品图片")}
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Choice id="bark-archive" label="保存到 Bark 历史" value={form.archive}
                    options={[["default", "跟随 App 设置"], ["yes", "保存"], ["no", "不保存"]]} onChange={(value) => update("archive", value)} />
                  {textField("ttl", "保存时效（秒）", "留空不指定过期", "number", { min: 0, max: 315360000, disabled: form.archive === "no" })}
                </div>
                <p className="text-xs text-muted-foreground">86400 = 1 天，604800 = 7 天。0 表示不保存；仅对已归档消息生效，由支持 ttl 的 Bark App 清理，非离线推送投递期限。</p>
                <details className="rounded-lg border border-border p-3">
                  <summary className="cursor-pointer text-sm font-medium">消息加密</summary>
                  <div className="mt-3 grid gap-3">
                    <Choice id="bark-encryption" label="加密方式" value={form.encryption}
                      options={[["none", "不加密"], ["GCM", "AES-GCM"], ["CBC", "AES-CBC（PKCS7）"]]} onChange={(value) => update("encryption", value)} />
                    {form.encryption !== "none" && <>
                      {textField("encryption_key", "AES 密钥", form.has_encryption_key ? "已保存，留空保持不变" : "16 / 24 / 32 字节", "password")}
                      {clearKey("encryption_key", "清除已保存的 AES 密钥（需先关闭加密）")}
                      <p className="text-xs text-muted-foreground">16 / 24 / 32 字节对应 AES-128 / 192 / 256，必须与 Bark App 的算法、模式和密钥一致。每次推送自动生成新的 IV。发送失败不会退回明文。</p>
                    </>}
                  </div>
                </details>
                <details className="rounded-lg border border-border p-3">
                  <summary className="cursor-pointer text-sm font-medium">声音、提醒级别与点击行为</summary>
                  <div className="mt-3 grid gap-4">
                    {textField("sound", "铃声名称", "留空使用 Bark 默认铃声，如 minuet")}
                    <Choice id="bark-level" label="提醒级别" value={form.level} onChange={(value) => update("level", value)}
                      options={[["passive", "被动（不亮屏）"], ["active", "正常"], ["timeSensitive", "时效性通知"], ["critical", "重要警告（需设备权限）"]]} />
                    {form.level === "critical" && textField("volume", "重要警告音量（0–10）", "5", "number", { min: 0, max: 10, required: true })}
                    {textField("badge", "App 角标（可选）", "留空不指定", "number", { min: 0, max: 99999 })}
                    {toggle("call", "重复播放铃声（约 30 秒）")}
                    {toggle("open_url", "点击通知打开优惠详情")}
                    {form.open_url && <>
                      <Choice id="bark-link-mode" label="链接打开方式" value={form.link_mode || "web"}
                        options={[["web", "网页链接（默认）"], ["app", "App 直达"]]} onChange={(value) => update("link_mode", value)} />
                      <p className="text-xs text-muted-foreground">{form.link_mode === "app"
                        ? "直接打开什么值得买 App 的好价详情。未安装 App 时不会自动回退；通知正文保留备用网页地址，可复制后手动打开。非好价详情链接仍使用网页地址。"
                        : "使用原始网页链接。系统可能唤起 App，具体取决于设备设置和目标 App 的通用链接支持。"}</p>
                    </>}
                    {toggle("auto_copy", "复制推送内容（新版 iOS 需手动长按）")}
                    {textField("copy_text", "自定义复制内容（可选）", "{url}")}
                  </div>
                </details>
              </>
            )}
            <DialogFooter className="gap-2">
              <Button type="button" variant="outline" onClick={test} disabled={testMut.isPending || saveMut.isPending}>{testMut.isPending ? "发送中…" : "发送测试"}</Button>
              <div className="flex-1" />
              <Button type="button" variant="outline" onClick={onClose}>取消</Button>
              <Button type="submit" disabled={saveMut.isPending || testMut.isPending}>保存</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
