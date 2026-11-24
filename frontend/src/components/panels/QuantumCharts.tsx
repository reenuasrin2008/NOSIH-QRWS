import React from "react";
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip } from "recharts";
import { QuantumMetrics } from "../../types/simulation";

export const QuantumCharts: React.FC<{ q: QuantumMetrics }> = ({ q }) => {
  const conv = q.convergence_history || [];
  const samples = q.top_samples.map((s) => ({
    bitstring: s.bitstring,
    prob: Number(((s.count / Math.max(1, q.shots)) * 100).toFixed(1)),
  }));

  return (
    <div className="space-y-2.5">
      {conv.length > 1 && (
        <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
          <div className="text-[10px] text-zinc-400 uppercase mb-1.5">COBYLA Energy Convergence</div>
          <div className="h-28">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={conv}>
                <XAxis dataKey="iter" stroke="#64748b" fontSize={9} />
                <YAxis stroke="#64748b" fontSize={9} width={38} />
                <Tooltip contentStyle={{ backgroundColor: "#11161f", borderColor: "#242c3a", fontSize: 10 }} />
                <Line type="monotone" dataKey="energy" stroke="#d97706" dot={false} strokeWidth={1.6} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {samples.length > 0 && (
        <div className="p-2 bg-[#0b0e14] border border-[#242c3a]">
          <div className="text-[10px] text-zinc-400 uppercase mb-1.5">Measured Bitstring Probability (%)</div>
          <div className="h-28">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={samples}>
                <XAxis dataKey="bitstring" stroke="#64748b" fontSize={8} />
                <YAxis stroke="#64748b" fontSize={9} width={30} />
                <Tooltip contentStyle={{ backgroundColor: "#11161f", borderColor: "#242c3a", fontSize: 10 }} />
                <Bar dataKey="prob" fill="#94a3b8" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
};
