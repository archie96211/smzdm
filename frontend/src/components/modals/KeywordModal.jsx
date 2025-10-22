import React, { useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";

const DEFAULT_KEYWORD = {
  keyword: "", category_id: "", brand_id: "", mall_id: "",
  order_type: "time", price_min: 0, price_max: 999999,
};

export default function KeywordModal({ mode, initial, onSubmit, onClose }) {
  const [form, setForm] = useState({ ...DEFAULT_KEYWORD, ...(initial || {}) });
  const title = mode === "edit" ? "编辑关键词" : "添加关键词";

  function submitForm(event) {
    event.preventDefault();
    onSubmit({ ...form, keyword: String(form.keyword || "").trim() });
  }

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submitForm} className="grid grid-cols-2 gap-4">
          <div className="col-span-2 grid gap-2">
            <Label>关键词</Label>
            <Input required pattern=".*\S.*" value={form.keyword}
              onChange={(e) => setForm({ ...form, keyword: e.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label>排序方式</Label>
            <Select value={form.order_type} onValueChange={(v) => setForm({ ...form, order_type: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="time">按时间</SelectItem>
                <SelectItem value="price_asc">价格从低到高</SelectItem>
                <SelectItem value="price_desc">价格从高到低</SelectItem>
                <SelectItem value="rating">按评分</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>分类 ID</Label>
            <Input value={form.category_id || ""}
              onChange={(e) => setForm({ ...form, category_id: e.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label>最低价格</Label>
            <Input type="number" min="0" value={form.price_min || 0}
              onChange={(e) => setForm({ ...form, price_min: Number(e.target.value) })} />
          </div>
          <div className="grid gap-2">
            <Label>最高价格</Label>
            <Input type="number" min="0"
              value={form.price_max >= 999999 ? "" : form.price_max}
              placeholder="不限"
              onChange={(e) => setForm({ ...form, price_max: e.target.value ? Number(e.target.value) : 999999 })} />
          </div>
          <div className="grid gap-2">
            <Label>品牌 ID</Label>
            <Input value={form.brand_id || ""}
              onChange={(e) => setForm({ ...form, brand_id: e.target.value })} />
          </div>
          <div className="grid gap-2">
            <Label>商城 ID</Label>
            <Input value={form.mall_id || ""}
              onChange={(e) => setForm({ ...form, mall_id: e.target.value })} />
          </div>
          <DialogFooter className="col-span-2 mt-2">
            <Button type="button" variant="outline" onClick={onClose}>取消</Button>
            <Button type="submit">保存</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
