import React, { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest, useManmanbuyStatus, useWechatStatus } from "@/helpers/api";

const channelNames = { bark: "Bark", dingtalk: "钉钉", wechat: "微信", wxpusher: "WxPusher" };

export default function ManmanbuyModal({ onClose }) {
  const { data: status } = useManmanbuyStatus();
  const qc = useQueryClient();
  const [login, setLogin] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState("");
  const [url, setUrl] = useState("");
  const [result, setResult] = useState(null);
  const [savedChecks, setSavedChecks] = useState([]);
  const [alerts, setAlerts] = useState(null);
  const [alertBusy, setAlertBusy] = useState(false);
  const { data: wechat } = useWechatStatus();
  const refresh = () => qc.invalidateQueries({ queryKey: ["manmanbuy-status"] });

  function loadChecks() {
    apiRequest("/api/purchase/price-checks").then(setSavedChecks).catch(() => {});
  }

  useEffect(loadChecks, []);
  useEffect(() => {
    apiRequest("/api/manmanbuy/alerts").then(setAlerts).catch((error) => toast.error(error.message));
  }, []);

  async function saveAlerts() {
    setAlertBusy(true);
    try {
      const data = await apiRequest("/api/manmanbuy/alerts", {
        method: "PUT", body: JSON.stringify(alerts.settings),
      });
      setAlerts(data);
      toast.success("慢慢买失效提醒设置已保存");
    } catch (error) { toast.error(error.message); }
    finally { setAlertBusy(false); }
  }

  useEffect(() => {
    if (!login) return;
    let cancelled = false;
    let timer;
    async function poll() {
      if (Date.now() > login.deadline) {
        setLogin(null);
        setHint("二维码已过期，请重新获取");
        return;
      }
      try {
        const data = await apiRequest(`/api/manmanbuy/login/${login.login_id}`);
        if (cancelled) return;
        if (data.state !== "waiting") {
          setLogin(null);
          setHint(data.state === "qr_expired" ? "二维码已过期，请重新获取" : data.message);
          refresh();
          return;
        }
      } catch (error) {
        if (!cancelled) { setLogin(null); setHint(error.message); }
        return;
      }
      if (!cancelled) timer = setTimeout(poll, 2500);
    }
    timer = setTimeout(poll, 2500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [login]);

  async function startLogin() {
    setBusy(true);
    setHint("");
    try {
      const data = await apiRequest("/api/manmanbuy/login", { method: "POST" });
      setLogin({ ...data, deadline: Date.now() + data.expires_in * 1000 });
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  }

  async function act(path, method = "POST") {
    setBusy(true);
    try {
      const data = await apiRequest(`/api/manmanbuy/${path}`, { method });
      setHint(data.message);
      setLogin(null);
      refresh();
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  }

  async function query(event) {
    event.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      setResult(await apiRequest("/api/manmanbuy/query", { method: "POST", body: JSON.stringify({ url }) }));
      loadChecks();
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); refresh(); }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>慢慢买历史价格</DialogTitle></DialogHeader>
        <p className="text-sm">{status?.message || "正在读取连接状态…"}</p>
        {status?.last_error && <p className="text-sm text-destructive">{status.last_error}</p>}
        <p className="text-sm text-muted-foreground">使用微信扫描慢慢买官方二维码并确认登录。会话保存在当前服务，查询无需浏览器常驻。</p>
        {login && <div className="grid justify-items-center gap-2">
          <img src={login.qr_url} alt="慢慢买官方微信登录二维码" className="size-48 rounded border bg-white p-2" referrerPolicy="no-referrer" />
          <p className="text-sm text-muted-foreground">请在一分钟内扫码确认，登录后自动更新</p>
        </div>}
        {hint && <p role="status" className="text-sm">{hint}</p>}
        <div className="flex flex-wrap gap-2">
          <Button onClick={startLogin} disabled={busy}>{login ? "刷新二维码" : status?.has_session ? "重新扫码登录" : "扫码连接慢慢买"}</Button>
          {status?.has_session && <>
            <Button variant="outline" onClick={() => act("validate")} disabled={busy}>验证连接</Button>
            <Button variant="ghost" onClick={() => act("session", "DELETE")} disabled={busy}>断开连接</Button>
          </>}
        </div>
        {alerts && <section className="grid gap-3 border-t pt-4 text-sm">
          <h3 className="font-medium">登录失效提醒</h3>
          <p className="text-muted-foreground">保存后，服务会每 15 分钟检查已连接的账号。确认失效后各渠道提醒一次，恢复连接后可再次提醒。</p>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={alerts.settings.enabled}
              onChange={(event) => setAlerts({ ...alerts, settings: { ...alerts.settings, enabled: event.target.checked } })} />
            启用失效提醒
          </label>
          {alerts.settings.enabled && <>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(channelNames).map(([channel, label]) => <label key={channel} className="flex items-center gap-2">
                <input type="checkbox" disabled={!alerts.available[channel]}
                  checked={alerts.settings.channels.includes(channel)}
                  onChange={(event) => setAlerts({ ...alerts, settings: {
                    ...alerts.settings,
                    channels: event.target.checked
                      ? [...alerts.settings.channels, channel]
                      : alerts.settings.channels.filter((item) => item !== channel),
                  } })} />
                {label}{!alerts.available[channel] && "（未配置）"}
              </label>)}
            </div>
            {alerts.settings.channels.includes("wechat") && <>
              <label htmlFor="mmb-wechat-target" className="font-medium">微信通知会话</label>
              <select id="mmb-wechat-target" className="rounded border bg-background p-2"
                value={alerts.settings.wechat_targets}
                onChange={(event) => setAlerts({ ...alerts, settings: {
                  ...alerts.settings, wechat_targets: event.target.value,
                  wechat_account_id: wechat?.account?.account_id || "",
                } })}>
                <option value="">请选择会话</option>
                {(wechat?.conversations || []).map((item) => <option
                  key={item.id} value={item.id}>
                  {item.remark || item.user_id || item.id}
                </option>)}
              </select>
            </>}
          </>}
          <Button variant="outline" onClick={saveAlerts} disabled={alertBusy}>保存提醒设置</Button>
        </section>}
        <form onSubmit={query} className="grid gap-2 border-t pt-4">
          <label htmlFor="mmb-product" className="text-sm font-medium">验证商品历史价格</label>
          <Input id="mmb-product" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="粘贴京东、淘宝或天猫完整商品链接" />
          <Button variant="outline" disabled={busy || !url || status?.state !== "connected"}>查询历史价格</Button>
        </form>
        {result && <div className="grid gap-1 rounded border p-3 text-sm">
          <p className="font-medium">{result.product_name || "商品查询结果"}</p>
          {result.has_history ? <>
            <p>来源历史最低：{result.lowest_price ?? "未知"} 元</p>
            <p>最低价日期：{result.lowest_date?.split("T")[0] || "未知"}</p>
            <p>60 天均价：{result.average_60_days ?? "未知"} 元</p>
          </> : <p>该商品暂未收录历史价格</p>}
          <p className="text-muted-foreground">{result.coverage}，不等同于个人券后实付价。</p>
        </div>}
        {savedChecks.length > 0 && <div className="grid gap-2 border-t pt-3 text-sm">
          <p className="font-medium">已保存的查询记录</p>
          {savedChecks.slice(0, 10).map((check) => <div key={check.id} className="rounded border border-border p-2">
            <p>{check.product_name || check.product_url}</p>
            <p className="text-muted-foreground">{check.checked_at} · 历史最低 {check.has_history ? `${check.lowest_price ?? "未知"} 元` : "暂无数据"}</p>
          </div>)}
        </div>}
        <a href="https://tool.manmanbuy.com/HistoryLowest.aspx" target="_blank" rel="noreferrer" className="text-sm underline">前往官方页面处理额外平台授权或验证</a>
      </DialogContent>
    </Dialog>
  );
}
