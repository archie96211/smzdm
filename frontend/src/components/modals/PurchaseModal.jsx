import React, { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ChevronDown, PackagePlus, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiRequest } from "@/helpers/api";

const CHANNELS = [
  { value: "jd", label: "京东" }, { value: "taobao", label: "淘宝" },
  { value: "tmall", label: "天猫" }, { value: "pdd", label: "拼多多" },
  { value: "douyin", label: "抖音" }, { value: "wechat", label: "微信" },
  { value: "offline", label: "线下" }, { value: "other", label: "其他" },
];
const EMPTY_PRODUCT = { name: "", measure_unit: "", package_label: "" };
const EMPTY_PURCHASE = { product_id: "", purchased_on: "", purchase_channel: "", order_number: "", store: "",
  paid_amount: "", package_count: "1", units_per_package: "", inner_package_count: "",
  inner_package_label: "", variant: "", note: "" };
const fieldClass = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";
const channelName = (value) => CHANNELS.find((item) => item.value === value)?.label || value || "渠道未填";

export default function PurchasePage() {
  const [products, setProducts] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [view, setView] = useState("history");
  const [query, setQuery] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const [visibleCount, setVisibleCount] = useState(20);
  const [expandedRecordId, setExpandedRecordId] = useState(null);
  const [productForm, setProductForm] = useState(EMPTY_PRODUCT);
  const [purchaseForm, setPurchaseForm] = useState(EMPTY_PURCHASE);
  const [editingId, setEditingId] = useState(null);
  const [editingProduct, setEditingProduct] = useState(false);
  const [linkForm, setLinkForm] = useState({ product_url: "", variant: "" });
  const [busy, setBusy] = useState(false);
  const selected = products.find((product) => String(product.id) === String(selectedId));

  const records = useMemo(() => products.flatMap((product) => product.purchases.map((record) => ({
    ...record, product_name: product.name, measure_unit: product.measure_unit,
    package_label: product.package_label,
  }))).sort((a, b) => (b.purchased_on || "").localeCompare(a.purchased_on || "") || b.id - a.id), [products]);
  const search = query.trim().toLocaleLowerCase();
  const filteredRecords = records.filter((record) =>
    (!channelFilter || record.purchase_channel === channelFilter) &&
    (!search || [record.product_name, record.variant, record.order_number, record.store, record.note, record.purchased_on]
      .some((value) => String(value || "").toLocaleLowerCase().includes(search))));
  const filteredProducts = products.filter((product) => !search ||
    [product.name, ...product.variant_summaries.map((item) => item.variant)]
      .some((value) => value.toLocaleLowerCase().includes(search)));

  async function refresh(preferredId) {
    const data = await apiRequest("/api/purchase/products");
    setProducts(data);
    const nextId = String(preferredId || (data.some((item) => String(item.id) === String(selectedId)) ? selectedId : data[0]?.id) || "");
    setSelectedId(nextId);
  }

  useEffect(() => { refresh().catch((error) => toast.error(error.message)); }, []);

  function openProduct(product) {
    setSelectedId(String(product.id));
    setView("product");
  }

  function openPurchase(product, record = null) {
    setSelectedId(String(product.id));
    setEditingId(record?.id || null);
    setPurchaseForm(record ? {
      product_id: String(product.id), purchased_on: record.purchased_on || "",
      purchase_channel: record.purchase_channel || "", order_number: record.order_number || "",
      store: record.store || "",
      paid_amount: record.paid_amount, package_count: String(record.package_count),
      units_per_package: record.units_per_package,
      inner_package_count: record.inner_package_count ? String(record.inner_package_count) : "",
      inner_package_label: record.inner_package_label || "", variant: record.variant || "",
      note: record.note || "",
    } : { ...EMPTY_PURCHASE, product_id: String(product.id) });
    setView("purchase-form");
  }

  function openProductForm(product = null) {
    setEditingProduct(Boolean(product));
    setProductForm(product ? { name: product.name, measure_unit: product.measure_unit,
      package_label: product.package_label } : EMPTY_PRODUCT);
    if (product) setSelectedId(String(product.id));
    setView("product-form");
  }

  async function saveProduct(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const data = await apiRequest(editingProduct ? `/api/purchase/products/${selectedId}` : "/api/purchase/products", {
        method: editingProduct ? "PUT" : "POST", body: JSON.stringify(productForm),
      });
      await refresh(data.id);
      setProductForm(EMPTY_PRODUCT);
      setEditingProduct(false);
      setView("product");
      toast.success("商品档案已保存");
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  }

  async function savePurchase(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = { ...purchaseForm, product_id: Number(selectedId),
        purchased_on: purchaseForm.purchased_on || null,
        package_count: Number(purchaseForm.package_count),
        inner_package_count: purchaseForm.inner_package_count ? Number(purchaseForm.inner_package_count) : null };
      await apiRequest(editingId ? `/api/purchase/records/${editingId}` : "/api/purchase/records", {
        method: editingId ? "PUT" : "POST", body: JSON.stringify(payload),
      });
      await refresh(selectedId);
      setEditingId(null);
      setPurchaseForm(EMPTY_PURCHASE);
      setView("product");
      toast.success("购买记录已保存");
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  }

  async function addLink(event) {
    event.preventDefault();
    setBusy(true);
    try {
      await apiRequest(`/api/purchase/products/${selectedId}/links`, {
        method: "POST", body: JSON.stringify(linkForm),
      });
      await refresh(selectedId);
      setLinkForm({ product_url: "", variant: "" });
      toast.success("商品链接已关联");
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  }

  async function deleteLink(link) {
    setBusy(true);
    try {
      await apiRequest(`/api/purchase/products/${selectedId}/links/${link.id}`, { method: "DELETE" });
      await refresh(selectedId);
      toast.success("商品链接已移除");
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  }

  async function deletePurchase(record) {
    if (!window.confirm("确定删除这条购买记录吗？")) return;
    setBusy(true);
    try {
      await apiRequest(`/api/purchase/records/${record.id}`, { method: "DELETE" });
      await refresh(selectedId);
      toast.success("购买记录已删除");
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  }

  async function deleteProduct() {
    if (!selected || !window.confirm(`确定删除空商品档案“${selected.name}”吗？`)) return;
    setBusy(true);
    try {
      await apiRequest(`/api/purchase/products/${selected.id}`, { method: "DELETE" });
      setSelectedId("");
      await refresh("");
      setView("products");
      toast.success("商品档案已删除");
    } catch (error) { toast.error(error.message); }
    finally { setBusy(false); }
  }

  function recordCard(record) {
    const product = products.find((item) => item.id === record.product_id);
    const expanded = expandedRecordId === record.id;
    return <article key={record.id} className="border-b border-border px-3 py-3.5 last:border-b-0 sm:px-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <button type="button" className="text-left font-medium hover:text-primary" onClick={() => openProduct(product)}>{record.product_name}</button>
            {record.variant && <span className="min-w-0 truncate text-sm text-muted-foreground" title={record.variant}>{record.variant}</span>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span>{record.purchased_on || "日期未填"}</span>
            <span className="rounded bg-muted px-1.5 py-0.5">{channelName(record.purchase_channel)}</span>
            {record.store && record.store !== channelName(record.purchase_channel) && <span className="max-w-52 truncate" title={record.store}>{record.store}</span>}
          </div>
        </div>
        <div className="shrink-0 text-right"><div className="font-semibold tabular-nums">¥{record.paid_amount}</div>
          <div className="text-xs text-muted-foreground">{record.package_count}{record.package_label} · {record.total_units}{record.measure_unit}</div></div>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs">
        <div className="font-medium text-muted-foreground">¥{record.price_per_unit}/{record.measure_unit}
          <span className="ml-2 font-normal">¥{record.price_per_package}/{record.package_label}
            {record.price_per_inner_package && ` · ¥${record.price_per_inner_package}/${record.inner_package_label}`}</span>
        </div>
        <div className="flex items-center gap-1">
          {(record.note || record.order_number) && <Button type="button" variant="ghost" size="sm" aria-expanded={expanded} onClick={() => setExpandedRecordId(expanded ? null : record.id)}>订单说明<ChevronDown size={14} className={`ml-1 transition-transform ${expanded ? "rotate-180" : ""}`} /></Button>}
          <Button type="button" variant="ghost" size="sm" onClick={() => openPurchase(product, record)}>修改</Button>
          <Button type="button" variant="ghost" size="sm" className="text-destructive" disabled={busy} onClick={() => deletePurchase(record)}>删除</Button>
        </div>
      </div>
      {expanded && <div className="mt-2 rounded-md bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
        {record.order_number && <p>订单号：{record.order_number}</p>}
        {record.note && <p>{record.note}</p>}
      </div>}
    </article>;
  }

  return <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-lg font-semibold">购买账本</h2>
        <p className="text-sm text-muted-foreground">记录实付价格，快速查看每次购买的单位成本。</p></div>
      {(view === "history" || view === "products") && <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => openProductForm()}><PackagePlus size={16} className="mr-2" />新建商品</Button>
        <Button onClick={() => { setQuery(""); setView("pick-product"); }}><Plus size={16} className="mr-2" />录入购买</Button></div>
      }
    </div>

    {(view === "history" || view === "products") && <p className="text-xs text-muted-foreground">{products.length} 个商品 · {records.length} 条购买 · {new Set(records.map((record) => record.purchase_channel).filter(Boolean)).size} 个渠道</p>}

    {(view === "history" || view === "products") && <>
      <div className="flex gap-2 border-b border-border" role="tablist" aria-label="购买记录视图">
        <button role="tab" aria-selected={view === "history"} className={`border-b-2 px-3 py-2 text-sm ${view === "history" ? "border-primary font-medium" : "border-transparent text-muted-foreground"}`} onClick={() => setView("history")}>购买历史</button>
        <button role="tab" aria-selected={view === "products"} className={`border-b-2 px-3 py-2 text-sm ${view === "products" ? "border-primary font-medium" : "border-transparent text-muted-foreground"}`} onClick={() => setView("products")}>商品档案</button>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1"><Search size={16} className="absolute left-3 top-2.5 text-muted-foreground" />
          <Input aria-label="搜索商品或购买记录" className="pl-9" value={query} onChange={(event) => { setQuery(event.target.value); setVisibleCount(20); }} placeholder="搜索商品、规格、店铺或备注" /></div>
        {view === "history" && <select aria-label="筛选购买渠道" className={`${fieldClass} sm:w-40`} value={channelFilter} onChange={(event) => { setChannelFilter(event.target.value); setVisibleCount(20); }}>
          <option value="">全部渠道</option>{CHANNELS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>}
      </div>
      {view === "history" ? <section aria-label="购买历史" className="grid gap-3">
        <p className="text-xs text-muted-foreground">找到 {filteredRecords.length} 条记录，按购买日期排序</p>
        <div className="overflow-hidden rounded-xl border border-border bg-card">{filteredRecords.slice(0, visibleCount).map(recordCard)}</div>
        {!filteredRecords.length && <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">没有符合条件的购买记录</div>}
        {filteredRecords.length > visibleCount && <Button variant="outline" onClick={() => setVisibleCount((count) => count + 20)}>显示更多</Button>}
      </section> : <section aria-label="商品档案" className="grid gap-3 sm:grid-cols-2">
        {filteredProducts.map((product) => <button key={product.id} type="button" onClick={() => openProduct(product)} className="rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/60 hover:bg-muted/30">
          <div className="flex items-start justify-between gap-2"><strong className="min-w-0 break-words">{product.name}</strong><span className="text-xs text-muted-foreground">{product.purchase_count} 次</span></div>
          <p className="mt-2 text-xs text-muted-foreground">{product.variant_summaries.length > 1 ? `${product.variant_summaries.length} 种规格` : product.best_price_per_unit ? `历史最低 ¥${product.best_price_per_unit}/${product.measure_unit}` : "暂无购买"}</p>
        </button>)}
        {!filteredProducts.length && <div className="col-span-full rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">没有找到商品档案</div>}
      </section>}
    </>}

    {view === "pick-product" && <section className="grid gap-3">
      <div className="flex items-center gap-2"><Button variant="ghost" size="sm" onClick={() => setView("history")}><ArrowLeft size={16} className="mr-1" />返回</Button><h3 className="font-semibold">选择已购商品</h3></div>
      <div className="relative"><Search size={16} className="absolute left-3 top-2.5 text-muted-foreground" /><Input aria-label="搜索商品档案" className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索商品名称或规格" /></div>
      <div className="grid gap-2 sm:grid-cols-2">{filteredProducts.map((product) => <button type="button" key={product.id} className="flex items-center justify-between rounded-lg border border-border p-3 text-left hover:border-primary/60" onClick={() => openPurchase(product)}><span>{product.name}</span><span className="text-xs text-muted-foreground">{product.purchase_count} 次 ›</span></button>)}</div>
      {!filteredProducts.length && <p className="text-sm text-muted-foreground">没有找到商品。可以先新建商品档案。</p>}
    </section>}

    {view === "product" && selected && <section className="grid gap-4">
      <div><Button variant="ghost" size="sm" onClick={() => setView("products")}><ArrowLeft size={16} className="mr-1" />全部商品</Button></div>
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-xl font-semibold">{selected.name}</h3><p className="text-sm text-muted-foreground">{selected.purchase_count} 次购买 · 按{selected.measure_unit}计价</p></div>
        <div className="flex gap-2"><Button variant="outline" onClick={() => openProductForm(selected)}>修改档案</Button><Button onClick={() => openPurchase(selected)}><Plus size={16} className="mr-1" />录入购买</Button></div></div>
      <div className="rounded-xl border border-border bg-card p-4 text-sm">
        <div className="font-medium">单位价格</div>
        {selected.variant_summaries.length > 1 ? <div className="mt-2 grid gap-2 sm:grid-cols-2">{selected.variant_summaries.map((item) => <div key={item.variant} className="rounded-lg bg-muted/40 p-2">{item.variant} · {item.purchase_count} 次<br /><span className="text-muted-foreground">平均 ¥{item.weighted_price_per_unit}/{selected.measure_unit} · 最低 ¥{item.best_price_per_unit}/{selected.measure_unit}</span></div>)}</div> : <p className="mt-1 text-muted-foreground">最近 ¥{selected.latest_price_per_unit ?? "—"}/{selected.measure_unit} · 最低 ¥{selected.best_price_per_unit ?? "—"}/{selected.measure_unit} · 加权平均 ¥{selected.weighted_price_per_unit ?? "—"}/{selected.measure_unit}</p>}
      </div>
      <div className="rounded-xl border border-border p-4 text-sm"><p className="font-medium">商品直达链接</p><p className="text-xs text-muted-foreground">用于精确匹配购买记录与查询历史价</p>
        <form onSubmit={addLink} className="mt-3 grid gap-2 sm:grid-cols-[1fr_9rem_auto]"><Input type="url" required placeholder="粘贴商品详情链接" value={linkForm.product_url} onChange={(event) => setLinkForm({ ...linkForm, product_url: event.target.value })} /><Input placeholder="对应规格（可选）" value={linkForm.variant} onChange={(event) => setLinkForm({ ...linkForm, variant: event.target.value })} /><Button type="submit" variant="outline" disabled={busy}>关联</Button></form>
        {selected.links.map((link) => <div key={link.id} className="mt-2 flex items-center gap-2 rounded-md bg-muted/30 p-2"><a href={link.product_url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate text-primary underline">{link.product_url}</a>{link.variant && <span>{link.variant}</span>}<Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => deleteLink(link)}>移除</Button></div>)}
      </div>
      <div className="flex items-center justify-between"><h4 className="font-semibold">历史购买</h4>{selected.purchase_count === 0 && <Button variant="outline" size="sm" className="text-destructive" disabled={busy} onClick={deleteProduct}>删除空档案</Button>}</div>
      {selected.purchases.length ? selected.purchases.map((record) => recordCard({ ...record, product_name: selected.name, measure_unit: selected.measure_unit, package_label: selected.package_label })) : <p className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">还没有购买记录</p>}
    </section>}

    {view === "product-form" && <section className="max-w-2xl rounded-xl border border-border bg-card p-5">
      <Button variant="ghost" size="sm" onClick={() => setView(editingProduct ? "product" : "products")}><ArrowLeft size={16} className="mr-1" />返回</Button>
      <h3 className="mt-2 text-lg font-semibold">{editingProduct ? "修改商品档案" : "新建商品档案"}</h3>
      <form onSubmit={saveProduct} className="mt-4 grid gap-3 sm:grid-cols-2"><div className="grid gap-1 sm:col-span-2"><Label>商品名称</Label><Input required value={productForm.name} onChange={(event) => setProductForm({ ...productForm, name: event.target.value })} /></div>
        <div className="grid gap-1"><Label>包装单位</Label><Input required value={productForm.package_label} onChange={(event) => setProductForm({ ...productForm, package_label: event.target.value })} placeholder="袋／包" /></div>
        <div className="grid gap-1"><Label>计价单位</Label><Input required value={productForm.measure_unit} onChange={(event) => setProductForm({ ...productForm, measure_unit: event.target.value })} placeholder="kg／张" /></div>
        <Button type="submit" disabled={busy} className="sm:col-span-2">保存商品档案</Button></form>
    </section>}

    {view === "purchase-form" && selected && <section className="max-w-2xl rounded-xl border border-border bg-card p-5">
      <Button variant="ghost" size="sm" onClick={() => setView("product")}><ArrowLeft size={16} className="mr-1" />返回商品</Button>
      <h3 className="mt-2 text-lg font-semibold">{editingId ? "修改购买记录" : "录入购买记录"}</h3>
      <p className="text-sm text-muted-foreground">{selected.name}</p>
      <form onSubmit={savePurchase} className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1"><Label htmlFor="purchase-date">购买日期</Label><Input id="purchase-date" type="date" value={purchaseForm.purchased_on} onChange={(event) => setPurchaseForm({ ...purchaseForm, purchased_on: event.target.value })} /></div>
        <div className="grid gap-1"><Label htmlFor="purchase-channel">购买渠道</Label><select id="purchase-channel" required className={fieldClass} value={purchaseForm.purchase_channel} onChange={(event) => setPurchaseForm({ ...purchaseForm, purchase_channel: event.target.value })}><option value="" disabled>选择购买渠道</option>{CHANNELS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div>
        <div className="grid gap-1 sm:col-span-2"><Label htmlFor="purchase-order-number">订单号（可选）</Label><Input id="purchase-order-number" autoComplete="off" value={purchaseForm.order_number} onChange={(event) => setPurchaseForm({ ...purchaseForm, order_number: event.target.value })} placeholder="同一订单的多件商品可填写相同订单号" /></div>
        <div className="grid gap-1 sm:col-span-2"><Label htmlFor="purchase-store">店铺（可选）</Label><Input id="purchase-store" value={purchaseForm.store} onChange={(event) => setPurchaseForm({ ...purchaseForm, store: event.target.value })} placeholder="例如：京东自营旗舰店" /></div>
        <div className="grid gap-1 sm:col-span-2"><Label htmlFor="purchase-variant">型号或规格（可选）</Label><Input id="purchase-variant" value={purchaseForm.variant} list="purchase-variants" onChange={(event) => setPurchaseForm({ ...purchaseForm, variant: event.target.value })} placeholder="例如：S 号／原味／10 kg 装" /><datalist id="purchase-variants">{selected.variant_summaries.filter((item) => item.variant !== "通用规格").map((item) => <option key={item.variant} value={item.variant} />)}</datalist></div>
        <div className="grid gap-1"><Label htmlFor="purchase-paid">实付总价（元）</Label><Input id="purchase-paid" required type="number" min="0" step="0.01" value={purchaseForm.paid_amount} onChange={(event) => setPurchaseForm({ ...purchaseForm, paid_amount: event.target.value })} /></div>
        <div className="grid gap-1"><Label htmlFor="purchase-count">包装数量（{selected.package_label}）</Label><Input id="purchase-count" required type="number" min="1" step="1" value={purchaseForm.package_count} onChange={(event) => setPurchaseForm({ ...purchaseForm, package_count: event.target.value })} /></div>
        <div className="grid gap-1 sm:col-span-2"><Label htmlFor="purchase-units">每{selected.package_label}含多少{selected.measure_unit}</Label><Input id="purchase-units" required type="number" min="0.0001" step="any" value={purchaseForm.units_per_package} onChange={(event) => setPurchaseForm({ ...purchaseForm, units_per_package: event.target.value })} /></div>
        <div className="grid gap-1"><Label htmlFor="purchase-inner-count">每{selected.package_label}内含多少小包装（可选）</Label><Input id="purchase-inner-count" type="number" min="1" step="1" value={purchaseForm.inner_package_count} onChange={(event) => setPurchaseForm({ ...purchaseForm, inner_package_count: event.target.value })} /></div>
        <div className="grid gap-1"><Label htmlFor="purchase-inner-label">小包装单位（可选）</Label><Input id="purchase-inner-label" value={purchaseForm.inner_package_label} onChange={(event) => setPurchaseForm({ ...purchaseForm, inner_package_label: event.target.value })} placeholder="袋／罐" /></div>
        <div className="grid gap-1 sm:col-span-2"><Label htmlFor="purchase-note">备注（可选）</Label><Input id="purchase-note" value={purchaseForm.note} onChange={(event) => setPurchaseForm({ ...purchaseForm, note: event.target.value })} placeholder="优惠券、订单说明等" /></div>
        <Button type="submit" disabled={busy} className="sm:col-span-2">{editingId ? "保存修改" : "保存购买记录"}</Button>
      </form>
    </section>}
  </div>;
}
