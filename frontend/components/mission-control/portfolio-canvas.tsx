"use client";

import { useOrchestratorStore } from "@/store/orchestrator-store";
import { motion } from "framer-motion";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
} from "recharts";
import { TrendingUp, TrendingDown, Activity, Shield, Target, Download, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";

const assetColors: Record<string, string> = {
  VTI: "#f59e0b",
  VOO: "#eab308",
  VEA: "#84cc16",
  VXUS: "#22c55e",
  VWO: "#10b981",
  BND: "#3b82f6",
  BNDX: "#6366f1",
  AGG: "#8b5cf6",
  VNQ: "#ec4899",
  VCSH: "#14b8a6",
  QQQ: "#f97316",
  CASH: "#64748b",
};

export function PortfolioCanvas() {
  const portfolio = useOrchestratorStore((state) => state.portfolio);
  const status = useOrchestratorStore((state) => state.status);

  const allocations = Object.entries(portfolio.allocations)
    .filter(([_, weight]) => weight > 0.001)
    .sort((a, b) => b[1] - a[1]);

  const chartData = allocations.map(([asset, weight]) => ({
    asset,
    weight: Math.round(weight * 100),
    fill: assetColors[asset] || "#666",
  }));

  const pieData = allocations.map(([asset, weight]) => ({
    name: asset,
    value: weight * 100,
    fill: assetColors[asset] || "#666",
  }));

  const metrics = portfolio.metrics;

  const handleExport = () => {
    const data = JSON.stringify(portfolio, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `portfolio-${new Date().toISOString().split("T")[0]}.json`;
    a.click();
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">Portfolio Allocation</h3>
        <Button
          variant="outline"
          size="sm"
          onClick={handleExport}
          disabled={allocations.length === 0}
        >
          <Download className="w-4 h-4 mr-1" />
          Export
        </Button>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <MetricCard
          label="Expected Return"
          value={metrics.expectedReturn}
          suffix="%"
          icon={TrendingUp}
          color="text-green-500"
        />
        <MetricCard
          label="Volatility"
          value={metrics.volatility}
          suffix="%"
          icon={Activity}
          color="text-amber-500"
        />
        <MetricCard
          label="Sharpe Ratio"
          value={metrics.sharpe}
          icon={Target}
          color="text-blue-500"
        />
        <MetricCard
          label="VaR (95%)"
          value={metrics.var95 ? metrics.var95 * 100 : undefined}
          suffix="%"
          icon={Shield}
          color="text-purple-500"
        />
      </div>

      {/* Allocation Chart */}
      {allocations.length > 0 ? (
        <div className="flex-1 overflow-y-auto min-h-0">
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={chartData} layout="vertical">
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10 }} />
              <YAxis
                type="category"
                dataKey="asset"
                tick={{ fontSize: 10 }}
                width={40}
              />
              <Tooltip
                formatter={(value) => [`${value}%`, "Allocation"]}
                contentStyle={{
                  backgroundColor: "hsl(var(--surface-1))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                }}
              />
              <Bar dataKey="weight" radius={[0, 4, 4, 0]}>
                {chartData.map((entry, index) => (
                  <Cell key={index} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {/* Allocation List */}
          <div className="mt-3 space-y-1.5 max-h-[100px] overflow-y-auto">
            {allocations.map(([asset, weight]) => (
              <motion.div
                key={asset}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-center justify-between text-sm"
              >
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: assetColors[asset] || "#666" }}
                  />
                  <span>{asset}</span>
                </div>
                <span className="font-mono">{(weight * 100).toFixed(1)}%</span>
              </motion.div>
            ))}
          </div>

          {/* Portfolio Explanation */}
          {portfolio.explanation && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-3 p-2.5 rounded-lg bg-blue-500/10 border border-blue-500/20"
            >
              <div className="flex items-center gap-2 mb-1.5">
                <MessageSquare className="w-3.5 h-3.5 text-blue-500" />
                <span className="text-xs font-medium text-blue-400">AI Explanation</span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {portfolio.explanation}
              </p>
            </motion.div>
          )}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-muted-foreground">
            <Activity className="w-12 h-12 mx-auto mb-2 opacity-30" />
            <p className="text-sm">
              {status === "running"
                ? "Waiting for allocation..."
                : "No allocation yet"}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

interface MetricCardProps {
  label: string;
  value?: number;
  suffix?: string;
  icon: React.ElementType;
  color: string;
}

function MetricCard({ label, value, suffix = "", icon: Icon, color }: MetricCardProps) {
  return (
    <div className="p-3 rounded-lg bg-surface-1 border border-border/30">
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-4 h-4 ${color}`} />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <div className="font-semibold">
        {value !== undefined ? (
          <motion.span
            key={value}
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {value.toFixed(2)}{suffix}
          </motion.span>
        ) : (
          <span className="text-muted-foreground">--</span>
        )}
      </div>
    </div>
  );
}
