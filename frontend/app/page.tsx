"use client";

import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Briefcase,
  Shield,
  Zap,
  BarChart3,
  GitBranch,
  CheckCircle2
} from "lucide-react";
import { Button } from "@/components/ui/button";

export default function HomePage() {
  const router = useRouter();

  const features = [
    {
      icon: Briefcase,
      title: "Mandate-Driven",
      description: "Define investment constraints, risk parameters, and ESG requirements",
    },
    {
      icon: GitBranch,
      title: "Multi-Candidate",
      description: "Generate and compare 3 diverse portfolio candidates (A/B/C)",
    },
    {
      icon: Shield,
      title: "Compliance & Red-Team",
      description: "Deterministic compliance checks and adversarial stress testing",
    },
    {
      icon: Zap,
      title: "Real-Time Progress",
      description: "Live workflow visualization with SSE streaming",
    },
    {
      icon: BarChart3,
      title: "Explainable Decisions",
      description: "Transparent scoring and selection with full audit trail",
    },
    {
      icon: CheckCircle2,
      title: "Production-Ready",
      description: "AKS deployment with observability and enterprise security",
    },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border/50">
        <div className="container mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center">
              <span className="text-white font-bold text-sm">IC</span>
            </div>
            <span className="font-semibold text-lg">IC Autopilot</span>
          </div>
          <Button variant="outline" onClick={() => router.push("/ic")}>
            Dashboard
          </Button>
        </div>
      </header>

      {/* Hero */}
      <main className="container mx-auto px-6 py-20">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center max-w-4xl mx-auto"
        >
          <h1 className="text-5xl font-bold tracking-tight mb-6">
            <span className="text-gold-gradient">Investment Committee</span>
            <br />
            Autopilot
          </h1>
          <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
            Enterprise-grade portfolio construction with multi-candidate generation,
            compliance verification, and adversarial stress testing.
            All orchestrated with real-time workflow visualization.
          </p>
          <div className="flex gap-4 justify-center">
            <Button
              size="lg"
              className="gap-2"
              onClick={() => router.push("/ic")}
            >
              Launch Dashboard
              <ArrowRight className="w-4 h-4" />
            </Button>
            <Button variant="outline" size="lg">
              View Documentation
            </Button>
          </div>
        </motion.div>

        {/* Features Grid */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-20"
        >
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 * index }}
              className="p-6 rounded-lg bg-card border border-border/50 hover:border-border transition-colors"
            >
              <feature.icon className="w-10 h-10 text-gold mb-4" />
              <h3 className="font-semibold text-lg mb-2">{feature.title}</h3>
              <p className="text-muted-foreground text-sm">{feature.description}</p>
            </motion.div>
          ))}
        </motion.div>

        {/* Workflow Preview */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
          className="mt-20 p-8 rounded-xl bg-card border border-border/50"
        >
          <h2 className="text-2xl font-bold mb-6 text-center">Workflow Stages</h2>
          <div className="flex flex-wrap justify-center gap-2">
            {[
              "Load Mandate",
              "Build Universe",
              "Compute Features",
              "Generate Candidates",
              "Verify Candidates",
              "Repair Loop",
              "Rank & Select",
              "Rebalance Plan",
              "Write Memo",
              "Audit Finalize",
            ].map((stage, index) => (
              <div
                key={stage}
                className="flex items-center gap-2 px-4 py-2 rounded-full bg-surface-2 border border-border/50 text-sm"
              >
                <span className="w-5 h-5 rounded-full bg-gold/20 text-gold flex items-center justify-center text-xs font-medium">
                  {index + 1}
                </span>
                {stage}
              </div>
            ))}
          </div>
        </motion.div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/50 mt-20">
        <div className="container mx-auto px-6 py-8 text-center text-muted-foreground text-sm">
          IC Autopilot - Built with Microsoft Agent Framework SDK
        </div>
      </footer>
    </div>
  );
}
